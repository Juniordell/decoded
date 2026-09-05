"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Chapter {
  title: string;
  start_seconds: number;
  end_seconds: number;
}

const SPEEDS = [0.75, 1, 1.25, 1.5, 2] as const;

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function AudioPlayer({
  src,
  arxivId,
  chapters = [],
  duration: knownDuration,
}: {
  src: string;
  arxivId: string;
  chapters?: Chapter[];
  duration?: number;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(knownDuration ?? 0);
  const [speed, setSpeed] = useState<number>(1);
  const [ready, setReady] = useState(false);
  const playReported = useRef(false);

  const storageKey = `podcast-progress:${arxivId}`;

  // Restaura posição salva
  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (!saved) return;
    const seconds = Number.parseFloat(saved);
    // Ignora se estava quase no fim — quem terminou quer recomeçar
    if (Number.isFinite(seconds) && seconds > 5) {
      setCurrent(seconds);
      if (audioRef.current) audioRef.current.currentTime = seconds;
    }
  }, [storageKey]);

  // Salva a cada 5 segundos de reprodução
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const audio = audioRef.current;
      if (!audio) return;
      if (audio.currentTime > 5 && audio.currentTime < audio.duration - 10) {
        localStorage.setItem(storageKey, String(audio.currentTime));
      } else if (audio.currentTime >= audio.duration - 10) {
        localStorage.removeItem(storageKey);
      }
    }, 5000);
    return () => clearInterval(id);
  }, [playing, storageKey]);

  // Media Session — controles na tela de bloqueio do celular
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;

    navigator.mediaSession.setActionHandler("play", () => void play());
    navigator.mediaSession.setActionHandler("pause", () => pause());
    navigator.mediaSession.setActionHandler("seekbackward", () => skip(-15));
    navigator.mediaSession.setActionHandler("seekforward", () => skip(30));

    return () => {
      navigator.mediaSession.setActionHandler("play", null);
      navigator.mediaSession.setActionHandler("pause", null);
      navigator.mediaSession.setActionHandler("seekbackward", null);
      navigator.mediaSession.setActionHandler("seekforward", null);
    };
  }, []);

  const reportPlay = useCallback(() => {
    if (playReported.current) return;
    playReported.current = true;
    const base = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/+$/, "");
    void fetch(`${base}/v1/podcasts/${arxivId}/play`, { method: "POST" }).catch(
      () => {},
    );
  }, [arxivId]);

  async function play() {
    const audio = audioRef.current;
    if (!audio) return;
    try {
      await audio.play();
      setPlaying(true);
      reportPlay();
    } catch {
      // Autoplay bloqueado — o usuário precisa clicar
    }
  }

  function pause() {
    audioRef.current?.pause();
    setPlaying(false);
  }

  function toggle() {
    if (playing) pause();
    else void play();
  }

  function skip(seconds: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(
      0,
      Math.min(audio.currentTime + seconds, audio.duration || 0),
    );
  }

  function seekTo(seconds: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = seconds;
    setCurrent(seconds);
  }

  function changeSpeed(next: number) {
    setSpeed(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  }

  const activeChapter = chapters.findIndex(
    (c) => current >= c.start_seconds && current < c.end_seconds,
  );

  const progress = duration > 0 ? (current / duration) * 100 : 0;

  return (
    <div className="bg-surface">
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onLoadedMetadata={(e) => {
          const audio = e.currentTarget;
          if (Number.isFinite(audio.duration)) setDuration(audio.duration);
          setReady(true);
        }}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onEnded={() => {
          setPlaying(false);
          localStorage.removeItem(storageKey);
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      {/* Controles */}
      <div className="flex items-center gap-4 px-5 py-4">
        <button
          type="button"
          onClick={toggle}
          disabled={!ready}
          aria-label={playing ? "Pause" : "Play"}
          className="flex h-11 w-11 shrink-0 items-center justify-center border border-accent text-accent transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-40"
        >
          {playing ? (
            <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
              <rect x="0" y="0" width="4.5" height="16" />
              <rect x="9.5" y="0" width="4.5" height="16" />
            </svg>
          ) : (
            <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
              <path d="M0 0 L14 8 L0 16 Z" />
            </svg>
          )}
        </button>

        <button
          type="button"
          onClick={() => skip(-15)}
          disabled={!ready}
          className="shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-subtle transition-colors hover:text-foreground disabled:opacity-40"
        >
          −15
        </button>

        <button
          type="button"
          onClick={() => skip(30)}
          disabled={!ready}
          className="shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-subtle transition-colors hover:text-foreground disabled:opacity-40"
        >
          +30
        </button>

        <div className="flex-1" />

        <span className="tnum shrink-0 font-mono text-[12px] text-subtle">
          {formatTime(current)} / {formatTime(duration)}
        </span>

        <div className="flex shrink-0 gap-1.5">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => changeSpeed(s)}
              className={`tnum font-mono text-[11px] transition-colors ${
                speed === s ? "text-accent" : "text-subtle hover:text-foreground"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      {/* Barra de progresso */}
      <div
        className="group relative h-2 cursor-pointer bg-border"
        onClick={(e) => {
          if (duration <= 0) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = (e.clientX - rect.left) / rect.width;
          seekTo(ratio * duration);
        }}
      >
        <div
          className="absolute inset-y-0 left-0 bg-accent"
          style={{ width: `${progress}%` }}
        />

        {/* Marcadores de capítulo */}
        {duration > 0 &&
          chapters.map((c) => (
            <div
              key={c.title}
              className="absolute inset-y-0 w-px bg-background"
              style={{ left: `${(c.start_seconds / duration) * 100}%` }}
            />
          ))}
      </div>

      {/* Capítulos */}
      {chapters.length > 0 && (
        <ol className="border-t border-border">
          {chapters.map((c, i) => (
            <li key={c.title}>
              <button
                type="button"
                onClick={() => {
                  seekTo(c.start_seconds);
                  if (!playing) void play();
                }}
                className={`flex w-full items-baseline gap-3.5 px-5 py-3 text-left transition-colors hover:bg-tint ${
                  activeChapter === i ? "bg-tint" : ""
                }`}
              >
                <span className="tnum shrink-0 font-mono text-[11px] text-subtle">
                  {formatTime(c.start_seconds)}
                </span>
                <span
                  className={`text-[16px] ${
                    activeChapter === i ? "text-accent" : ""
                  }`}
                >
                  {c.title}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
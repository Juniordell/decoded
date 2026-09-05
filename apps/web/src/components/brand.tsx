/**
 * Elementos da marca.
 *
 * Os dois de cima da marca são fragmentos em opacidade reduzida — notação, o
 * paper como chega. Os dois de baixo são contínuos: linguagem, o paper depois
 * que o Decoded leu. A última linha para antes do fim, como a última linha de
 * um parágrafo.
 */

export function DecodedLogo({
  width = 126,
  className,
  tone = "pine",
}: {
  width?: number;
  className?: string;
  tone?: "pine" | "reversed";
}) {
  // "reversed" é sempre sobre a faixa de tinta do rodapé, que não muda com o
  // tema — por isso valores fixos em vez de tokens.
  const mark = tone === "reversed" ? "#63BE93" : "var(--accent)";
  const word = tone === "reversed" ? "#F7F6F1" : "var(--foreground)";

  return (
    <svg
      viewBox="0 0 272 64"
      width={width}
      height={(width * 64) / 272}
      className={className}
      role="img"
      aria-label="Decoded"
    >
      <g fill="none" stroke={mark} strokeWidth="7">
        <g opacity="0.45">
          <path d="M4 13h14M26 13h10M44 13h16" />
          <path d="M4 26h24M36 26h24" />
        </g>
        <path d="M4 39h56" />
        <path d="M4 52h40" />
      </g>
      <text
        x="86"
        y="47"
        fontFamily="var(--font-serif), Georgia, serif"
        fontSize="40"
        fontWeight="600"
        letterSpacing="-1"
        fill={word}
      >
        Decoded
      </text>
    </svg>
  );
}

/** Só o ícone — favicon, cartões sociais, marcadores compactos. */
export function DecodedMark({
  size = 22,
  className,
  tone = "pine",
}: {
  size?: number;
  className?: string;
  tone?: "pine" | "reversed";
}) {
  const stroke = tone === "reversed" ? "#63BE93" : "var(--accent)";

  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
    >
      <g fill="none" stroke={stroke} strokeWidth="7">
        <g opacity="0.45">
          <path d="M4 13h14M26 13h10M44 13h16" />
          <path d="M4 26h24M36 26h24" />
        </g>
        <path d="M4 39h56" />
        <path d="M4 52h40" />
      </g>
    </svg>
  );
}

/**
 * The Resolve — régua que começa fragmentada e vira contínua. Separa as
 * camadas de um decode. Sempre no sentido da leitura, fragmentos primeiro.
 */
export function Resolve({ className = "my-8" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 420 12"
      preserveAspectRatio="none"
      width="100%"
      height="10"
      className={className}
      role="presentation"
      style={{ display: "block", overflow: "visible" }}
    >
      <g stroke="var(--accent)" strokeWidth="2.5" fill="none" strokeOpacity="0.9">
        <path d="M0 6h9M16 6h9M32 6h15M54 6h11M72 6h22M101 6h18M126 6h30M163 6h24M194 6h226" />
      </g>
    </svg>
  );
}

/**
 * The Layer Stack — cinco barras, cada uma menor e mais clara que a de cima:
 * as cinco formas de explicar o mesmo paper. Fica atrás do conteúdo, em
 * opacidade baixa, e nunca compete com o texto.
 */
export function LayerStack({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 420 128"
      preserveAspectRatio="none"
      className={className}
      aria-hidden="true"
    >
      <g fill="currentColor">
        <rect x="0" y="4" width="420" height="12" />
        <rect x="0" y="30" width="340" height="12" />
        <rect x="0" y="56" width="262" height="12" />
        <rect x="0" y="82" width="180" height="12" />
        <rect x="0" y="108" width="104" height="12" />
      </g>
    </svg>
  );
}

/**
 * Texto redigido — o paper ainda não decodificado. Barras no lugar das
 * palavras que ainda não existem.
 */
export function Redacted({
  className,
  width = 150,
  seed = 0,
}: {
  className?: string;
  width?: number;
  seed?: number;
}) {
  // Quatro larguras por linha, variadas de forma determinística pelo seed,
  // para que duas linhas seguidas não fiquem idênticas.
  const rows = [
    [86, 40],
    [54, 72],
  ];
  const shift = (seed % 3) * 8;

  return (
    <svg
      viewBox="0 0 200 26"
      width={width}
      height={(width * 26) / 200}
      className={className}
      aria-hidden="true"
      style={{ display: "block", flex: "none" }}
    >
      <g fill="var(--accent-soft)">
        {rows.map((row, i) => {
          const first = row[0] + (i === 0 ? shift : -shift);
          const second = row[1] - (i === 0 ? shift : -shift);
          return (
            <g key={i}>
              <rect x="0" y={i === 0 ? 2 : 15} width={first} height="7" />
              <rect
                x={first + 8}
                y={i === 0 ? 2 : 15}
                width={second}
                height="7"
              />
            </g>
          );
        })}
      </g>
    </svg>
  );
}

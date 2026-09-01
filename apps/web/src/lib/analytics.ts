"use client";

import posthog from "posthog-js";

/**
 * Nomes de evento centralizados.
 *
 * String solta espalhada pelo código vira `paper_viewed`, `paperViewed`
 * e `paper-view` em três arquivos diferentes, e o funil não fecha.
 */
export const EVENTS = {
  // Descoberta
  FEED_VIEWED: "feed_viewed",
  FEED_FILTERED: "feed_filtered",
  FEED_PAGINATED: "feed_paginated",
  SEARCH_PERFORMED: "search_performed",
  SEARCH_RESULT_CLICKED: "search_result_clicked",

  // Leitura
  PAPER_VIEWED: "paper_viewed",
  PAPER_SECTION_VIEWED: "paper_section_viewed",
  VOCAB_TERM_OPENED: "vocab_term_opened",
  PDF_CLICKED: "pdf_clicked",

  // Modos
  MODE_TAB_CLICKED: "mode_tab_clicked",
  MODE_GENERATE_CLICKED: "mode_generate_clicked",
  MODE_GENERATED: "mode_generated",
  MODE_OUT_OF_CREDITS: "mode_out_of_credits",

  // Tópicos
  PULSE_VIEWED: "pulse_viewed",
  TOPIC_VIEWED: "topic_viewed",
  AUTHOR_VIEWED: "author_viewed",

  // Conta
  PAPER_SAVED: "paper_saved",
  PAPER_UNSAVED: "paper_unsaved",
  FOLLOWED: "followed",
  UNFOLLOWED: "unfollowed",
  SIGNED_UP: "signed_up",
} as const;

export type EventName = (typeof EVENTS)[keyof typeof EVENTS];

export function capture(
  event: EventName,
  properties?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") return;
  try {
    posthog.capture(event, properties);
  } catch {
    // Analytics nunca pode quebrar a página
  }
}

export function identify(
  userId: string,
  traits?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") return;
  try {
    posthog.identify(userId, traits);
  } catch {
    // silencioso
  }
}

export function reset(): void {
  if (typeof window === "undefined") return;
  try {
    posthog.reset();
  } catch {
    // silencioso
  }
}

export function useFeatureFlag(key: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return posthog.isFeatureEnabled(key) ?? false;
  } catch {
    return false;
  }
}

export { posthog };
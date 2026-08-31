"""Renderização do digest em HTML e texto puro.

Regras de HTML para email:
- Layout com tabelas. Flexbox e grid não funcionam no Outlook.
- Estilos inline. <style> no head é removido por vários clientes.
- Largura fixa de 600px, o consenso da indústria.
- Sem imagens de fundo, sem web fonts, sem JavaScript.
"""

from __future__ import annotations

import html
from datetime import datetime

# Paleta do Decoded, convertida de OKLCH para hex — email não suporta oklch()
INK = "#0A1628"
BONE = "#F5F1E8"
ACCENT = "#C1440E"
MUTED = "#6B7A94"
BORDER = "#D8D2C0"
CARD = "#FFFFFF"


def _esc(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def render_html(
    subject: str,
    content: dict,
    site_url: str,
    week_start: datetime,
) -> str:
    papers = content.get("papers", [])
    preview = content.get("preview", "")
    following = content.get("following", {})
    personalized = content.get("personalized", False)
    token = content.get("unsubscribe_token", "")

    week_label = week_start.strftime("%B %-d, %Y")

    # Rodapé explicando a personalização
    follow_note = ""
    if personalized:
        parts = []
        if topics := following.get("topics"):
            parts.append(f"{len(topics)} topic{'s' if len(topics) != 1 else ''}")
        if authors := following.get("authors"):
            parts.append(f"{len(authors)} author{'s' if len(authors) != 1 else ''}")
        if insts := following.get("institutions"):
            parts.append(f"{len(insts)} institution{'s' if len(insts) != 1 else ''}")
        if parts:
            follow_note = f"Selected from what you follow: {', '.join(parts)}."
    else:
        follow_note = (
            "You're getting the general feed. "
            f'<a href="{site_url}/topics" style="color:{ACCENT};text-decoration:none;">'
            "Follow topics</a> to personalize this."
        )

    paper_rows = []
    for i, p in enumerate(papers):
        arxiv_id = _esc(p.get("arxiv_id"))
        url = f"{site_url}/paper/{arxiv_id}"
        title = _esc(p.get("title"))
        one_sentence = _esc(p.get("one_sentence"))
        reason = _esc(p.get("reason"))
        is_decoded = p.get("is_decoded")

        border_top = (
            f"border-top:1px solid {BORDER};" if i > 0 else ""
        )

        summary_block = ""
        if one_sentence:
            summary_block = f"""
                    <p style="margin:10px 0 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;color:#4A5568;">
                      {one_sentence}
                    </p>"""
        elif not is_decoded:
            summary_block = f"""
                    <p style="margin:10px 0 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.5;color:{MUTED};font-style:italic;">
                      Not decoded yet — read the abstract on the site.
                    </p>"""

        paper_rows.append(f"""
          <tr>
            <td style="padding:24px 0;{border_top}">
              <p style="margin:0 0 8px;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:{ACCENT};">
                {reason}
              </p>
              <a href="{url}" style="text-decoration:none;">
                <h2 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:20px;line-height:1.3;font-weight:600;color:{INK};">
                  {title}
                </h2>
              </a>{summary_block}
              <p style="margin:12px 0 0;">
                <a href="{url}" style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:{ACCENT};text-decoration:none;">
                  Read decoded &rarr;
                </a>
              </p>
            </td>
          </tr>""")

    papers_html = "".join(paper_rows)

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:{BONE};">

  <!-- Texto de preview, oculto no corpo mas lido pela inbox -->
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    {_esc(preview)}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{BONE};">
    <tr>
      <td align="center" style="padding:32px 16px;">

        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">

          <!-- Cabeçalho -->
          <tr>
            <td style="padding-bottom:28px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <a href="{site_url}" style="text-decoration:none;">
                      <span style="font-family:Georgia,'Times New Roman',serif;font-size:24px;color:{INK};">Decoded</span>
                    </a>
                  </td>
                  <td align="right" style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:{MUTED};">
                    Week of {week_label}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Papers -->
          <tr>
            <td style="background-color:{CARD};padding:8px 32px 24px;border:1px solid {BORDER};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                {papers_html}
              </table>
            </td>
          </tr>

          <!-- Rodapé -->
          <tr>
            <td style="padding:28px 4px 0;">
              <p style="margin:0 0 14px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:13px;line-height:1.6;color:{MUTED};">
                {follow_note}
              </p>
              <p style="margin:0;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:10px;letter-spacing:1.2px;text-transform:uppercase;color:{MUTED};">
                <a href="{site_url}" style="color:{MUTED};text-decoration:none;">Decoded</a>
                &nbsp;&middot;&nbsp;
                <a href="{site_url}/settings" style="color:{MUTED};text-decoration:none;">Preferences</a>
                &nbsp;&middot;&nbsp;
                <a href="{site_url}/unsubscribe?token={_esc(token)}" style="color:{MUTED};text-decoration:none;">Unsubscribe</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_text(
    subject: str,
    content: dict,
    site_url: str,
    week_start: datetime,
) -> str:
    """
    Versão em texto puro.

    Não é opcional: filtros de spam penalizam emails só-HTML, e alguns
    clientes ainda preferem texto.
    """
    papers = content.get("papers", [])
    token = content.get("unsubscribe_token", "")
    week_label = week_start.strftime("%B %-d, %Y")

    lines = [
        "DECODED",
        f"Week of {week_label}",
        "",
        "=" * 60,
        "",
    ]

    for p in papers:
        lines.append(p.get("reason", "").upper())
        lines.append(p.get("title", ""))
        if p.get("one_sentence"):
            lines.append("")
            lines.append(p["one_sentence"])
        lines.append("")
        lines.append(f"{site_url}/paper/{p.get('arxiv_id')}")
        lines.append("")
        lines.append("-" * 60)
        lines.append("")

    lines.extend(
        [
            "",
            f"Decoded — {site_url}",
            f"Preferences: {site_url}/settings",
            f"Unsubscribe: {site_url}/unsubscribe?token={token}",
        ]
    )

    return "\n".join(lines)
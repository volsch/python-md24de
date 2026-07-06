"""Static, session-independent legal notices used in reports.

Kept separate from :mod:`md24de._pdf` (which pulls in the optional
``reportlab`` dependency) so that callers can retrieve this notice text
without needing the ``pdf`` extra installed.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Voluntary orientation note followed by clarifications on the UVI's non-binding
# character. Not a § 6a HeizkostenV Pflichtangabe — the law only mandates the
# three data items (consumption, month/year and average comparisons).
UVI_DISCLOSURE_NOTE = (
    "Diese Informationen dienen lediglich Ihrer Orientierung. Die endgültige Abrechnung "
    "erfolgt jährlich. Die unterjährige Verbrauchsinformation (UVI) ersetzt keine Abrechnung "
    "und ist für die monatliche Abrechnung nicht geeignet; auf ihrer Grundlage können "
    "Heizkostenvorschüsse weder angehoben noch gekürzt werden. Die Jahresendabrechnung kann "
    "aufgrund von Umlageschlüsseln und Korrekturwerten von den hier dargestellten Werten "
    "abweichen; ihre formelle und materielle Wirksamkeit bleibt von eventuellen Fehlern in "
    "der UVI unberührt. Die Aufsummierung der UVI über das Jahr ergibt weder den "
    "Jahresverbrauch noch einen Hinweis auf die Kostenentwicklung."
)


def get_uvi_disclosure_note() -> str:
    """Return the mandatory § 6a Abs. 2 HeizkostenV UVI disclosure note.

    The text is static and session-independent — it does not depend on any
    portal access or parsed report data, and is safe to call without the
    ``pdf`` optional extra installed.

    Returns:
        The German disclosure note text shown under "Hinweis:" in the
        rendered UVI PDF.
    """
    _log.debug("Returning UVI disclosure note (%d chars)", len(UVI_DISCLOSURE_NOTE))
    return UVI_DISCLOSURE_NOTE

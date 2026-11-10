"""Adjacent-sentence causal links; no package dependencies beyond core."""
from __future__ import annotations

MATURITY = "incubating"

import re
from rag_research_agent.core.types import CausalLink, LinkType

# (prefix regex, reverse direction, link type); more specific reversals first.
LINK_MARKERS = (
    (r"^(?:그러나|하지만)\s+실제로는", True, LinkType.CONTRADICTS),
    (r"^(?:그 이유는|원인은|이는\s+.*때문)", True, LinkType.CAUSES),
    (r"^(?:그 결과|이에 따라|따라서|결국|그래서)(?:\s|[,，]|$)", False, LinkType.CAUSES),
)


class RuleLinkBuilder:
    def __init__(self, source_text=""):
        self.text = source_text

    def with_text(self, text):
        return RuleLinkBuilder(text)

    def build(self, segments):
        ordered = sorted(segments, key=lambda s: s.start)
        links = []
        for previous, current in zip(ordered, ordered[1:]):
            if previous.source != current.source:
                continue
            text = self.text[current.start:current.end].lstrip()
            for marker, reverse, kind in LINK_MARKERS:
                if re.search(marker, text):
                    src, dst = (current, previous) if reverse else (previous, current)
                    links.append(CausalLink(src.segment_id, dst.segment_id, kind, "rule"))
                    break
        return links

"""Check explicit claims of past experience before streaming a peer's sentence."""
from __future__ import annotations

import re
import unicodedata

from ...session import Session
from ..base import TextSink


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    text = re.sub(r"\b(i|we|they|you)'ve\b", r"\1 have", text)
    return " ".join(text.split()).strip(" .!?。！？")


# Target assertions of experience or customary practice, leaving ordinary reasoning
# ("I thought", "I would", "we could") available to speakers in both supported languages.
_FREQUENCY = r"(?:always|usually|often|sometimes|routinely|traditionally|never|rarely)"
_COGNITION = r"(?:think|thought|wonder|assum|reason|consider|discuss|mention|believ|explain|guess|suspect|imagin)"
_HISTORY = re.compile(
    rf"\b(?:i|we) (?:have|had) (?:{_FREQUENCY} )?(?:been (?!{_COGNITION})|"
    rf"(?!{_COGNITION})\w+ed\b|seen\b|heard\b|done\b|used to\b)"
    r"|\b(?:i|we) (?:was |were |got )(?:told|taught|trained|shown)\b"
    r"|\b(?:i|we) (?:saw|heard|observed|witnessed|used to (?!think\b|believe\b|assume\b|wonder\b)|"
    r"remember (?:when|learning|being told|seeing|hearing))\b"
    rf"|\b(?:i|we|they|everyone|everybody) {_FREQUENCY} (?!{_COGNITION})\w+"
    r"|\b(?:the|our) [\w-]+(?:ers|ors|ists|ants|ents|ees|ians) (?:always|usually|routinely|traditionally) "
    r"(?:sign|choose|say|write|mark|use|check|sort|decide|agree|prefer|ask|discuss|collect|record)\b"
    rf"|\b(?:thing|way|how|what) (?:that )?we (?!{_FREQUENCY}\b|{_COGNITION}|have\b|had\b|can\b|"
    r"could\b|might\b|should\b|would\b|mean\b|know\b|need\b|wouldn't\b)\w+"
    r"|(?:들었|들어\s*왔|배웠|배워\s*왔|가르쳐\s*주셨|겪었|목격했|직접\s*봤|본\s*적이|해\s*왔|하곤\s*했)"
    r"|(?:우리(?:는|가|들이?)?|저희(?:는|가)?)\s+(?:늘|항상|평소에?|예전부터)"
)
_QUOTED = re.compile(r'“([^”]+)”|"([^"]+)"|‘([^’]+)’')
_SAY = r"(?:said|says|reported|recalled|wrote|noted|told (?:me|us))"
_CLAUSE_BREAK = re.compile(r"[,;—]|\b(?:because|but)\b")


def _establishes(source: str, claim: str) -> bool:
    """A source must assert the historical clause in its own voice."""
    for part in re.split(r"(?<=[.!?。！？])\s+|\n", source):
        if part.rstrip().endswith(("?", "？")):
            continue
        text = _normalized(part)
        if re.search(r"\b(?:if|whether|unless|suppose|imagine)\b|(?:다면|었으면|라면)", text):
            continue
        if text == claim:
            return True
        # Do not inherit first-person ownership from a quote inside a source sentence.
        outside_quotes = _normalized(_QUOTED.sub("…", part))
        if any(_normalized(clause) == claim for clause in _CLAUSE_BREAK.split(outside_quotes)):
            return True
    return False


def _attributed(before: str, after: str, names: tuple[str, ...]) -> bool:
    for name in names:
        who = re.escape(_normalized(name))
        if re.search(rf"(?<!\w){who}\s+{_SAY}(?:\s+(?:that|earlier))?[, :]*$", before):
            return True
        if re.match(rf"^[, ]*(?:the )?{who}\s+{_SAY}\b", after):
            return True
        if re.search(rf"{who}(?:은|는|이|가)\s*$", before) and re.match(r"^(?:이?라고|라며|고)\s*", after):
            return True
    return False


def unsupported_history(sentence: str, own: list[str], reports: list[tuple[tuple[str, ...], str]]) -> bool:
    """Match a historical assertion to an explicit source, respecting ownership of firsthand accounts.

    Sources are assigned beliefs/explanation and public accounts with speaker aliases.
    A quoted rule without an account of how it was learned cannot establish such an experience.
    """
    text = _normalized(sentence)
    if not _HISTORY.search(text):
        return False
    for match in reversed(list(_QUOTED.finditer(sentence))):
        claim = _normalized(next(group for group in match.groups() if group is not None))
        if not _HISTORY.search(claim):
            continue
        before = _normalized(sentence[:match.start()])
        after = _normalized(sentence[match.end():])
        if not any(_attributed(before, after, names) and _establishes(source, claim) for names, source in reports):
            return True
        # Check the rest independently; quoting a speaker cannot authorize an added claim of my own.
        sentence = sentence[:match.start()] + "…" + sentence[match.end():]
    for clause in _CLAUSE_BREAK.split(_normalized(sentence)):
        claim = clause.strip()
        mark = _HISTORY.search(claim)
        if not mark:
            continue
        if re.search(r"\b(?:if|whether|suppose|imagine)\s*$", claim[:mark.start()]):
            continue
        if re.search(r"(?:다면|더라면|었으면|았다면|했다면)", claim[mark.start():]):
            continue
        if not any(_establishes(source, claim) for source in own):
            return True
    return False


class PeerSpeechSink:
    """Release checked sentences incrementally. Cancelling a turn discards its pending sentence."""

    def __init__(self, session: Session, peer_id: str, out: TextSink):
        self.session, self.peer_id, self.out = session, peer_id, out
        state = session.state_of(peer_id)
        ideas = ([b.text for b in state.beliefs] + [state.explanation]) if state else []
        self.own = [idea for idea in ideas if idea]
        self.idea = next((idea for idea in ideas if idea and len(idea) <= 400), "")
        self.reports: list[tuple[tuple[str, ...], str]] = []
        aliases = {"user": ("learner", "학습자"), "tutor": ("tutor", "튜터")}
        for message in session.transcript:
            self.reports.append(((message.speaker_name, *aliases.get(message.role, ())), message.text))
            if message.speaker_id == peer_id:
                self.own.append(message.text)
        self.buffer: list[str] = []
        self.quote_end = ""
        self.terminal = self.overflow = self.spoken = False
        self.suppressed = 0

    async def write(self, chunk: str) -> None:
        for char in chunk:
            if self.terminal and not self.quote_end and char.isspace():
                await self._sentence()
            # Provider requests are capped at 400 tokens. Bound pathological unpunctuated output too.
            if len(self.buffer) < 16384:
                self.buffer.append(char)
            else:
                self.overflow = True
            if self.quote_end and char == self.quote_end:
                self.quote_end = ""
            elif not self.quote_end and char in ('“', '‘', '"'):
                self.quote_end = {'“': '”', '‘': '’', '"': '"'}[char]
                self.terminal = False
            elif char not in ")]}":
                self.terminal = char in ".!?。！？"

    async def _sentence(self) -> None:
        sentence = "".join(self.buffer)
        self.buffer.clear()
        if self.overflow or unsupported_history(sentence, self.own, self.reports):
            self.suppressed += 1
        elif sentence.strip():
            await self.out.write(sentence if self.spoken else sentence.lstrip())
            self.spoken = True
        self.terminal = self.overflow = False

    async def flush(self) -> None:
        await self._sentence()
        if self.suppressed:
            self.session.log("peer.history_suppressed", {"agentId": self.peer_id, "count": self.suppressed})
            if not self.spoken:
                if self.session.language == "ko":
                    fallback = f"제가 가진 생각은 이래요. {self.idea}" if self.idea else "아직 잘 모르겠어요."
                else:
                    fallback = f"My starting assumption is this. {self.idea}" if self.idea else "I'm still unsure."
                await self.out.write(fallback)

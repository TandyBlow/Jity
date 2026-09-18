"""Download the Chinese Stanza models used by the state segmenter."""

import stanza


if __name__ == "__main__":
    stanza.download(
        "zh-hans",
        processors="tokenize,pos,lemma,depparse",
    )

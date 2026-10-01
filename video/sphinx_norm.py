"""Text normalisation for PocketSphinx forced alignment."""
import re

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def two(n):
    if n < 20:
        return [ONES[n]]
    t, o = divmod(n, 10)
    return [TENS[t]] + ([ONES[o]] if o else [])


def number_words(n):
    if n < 100:
        return two(n)
    if n < 1000:
        h, r = divmod(n, 100)
        return [ONES[h], "hundred"] + (two(r) if r else [])
    th, r = divmod(n, 1000)
    return number_words(th) + ["thousand"] + (number_words(r) if r else [])


def year_words(y):
    if 2000 <= y <= 2009:
        return ["two", "thousand"] + ([ONES[y - 2000]] if y > 2000 else [])
    hi, lo = divmod(y, 100)
    return two(hi) + (["hundred"] if lo == 0 else (["oh", ONES[lo]] if lo < 10 else two(lo)))


def normalise(token):
    t = token.lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9' -]", " ", t.replace("-", " "))
    out = []
    for p in t.split():
        p = p.strip("'")
        if not p:
            continue
        if p.isdigit():
            n = int(p)
            out += year_words(n) if 1900 <= n <= 2099 else number_words(n)
        else:
            out.append(p)
    return out

---
title: Fidelity sample
tags: [a, b]
---

# Heading one

## Heading two with `code` and *emphasis*

### Heading three

Plain paragraph with **bold**, *italic*, ***both***, ~~strike~~, `inline code`, an [inline link](https://example.com/a?b=c), a bare <https://example.org/auto> autolink, a reference [link][ref] and a footnote[^1]. A hard
break follows this line  
and this is the next line. Here is an image: ![the alt text](pic.png "title").

[ref]: https://example.net/ref
[^1]: The footnote text.

> A block quote that is long enough to need wrapping when the terminal is narrow, with *emphasis* inside it.
>
> > A nested quote.

> [!WARNING]
> A callout with an icon and a tint.

- bullet one
  - nested bullet
    - deeper bullet with a long line that has to wrap around the edge of the narrow column to show the hanging indent
- bullet two
  1. ordered inside
  2. second
- [ ] open task
- [x] done task

1. first
2. second
   - mixed nesting
3. third

| Name | Qty | Notes |
|:-----|----:|:-----:|
| apple | 3 | `fruit` and **bold** |
| 日本語 | 12 | wide characters in a cell |
| a long cell that has to wrap inside its column when the table is narrower than its text | 7 | x |

```rust
fn main() {
    // a comment
    let v: Vec<u32> = (0..10).collect();
    println!("{:?}", v);
}
```

```python
def f(n):
    return [i * 2 for i in range(n)]  # comment
```

```
no language, kept as is
```

---

Emoji and wide text: 🚀 👨‍👩‍👧 ❤️ 🇯🇵 and 日本語のテキストはここにあります。中文文字。한국어 텍스트 wraps by grapheme cluster, never in the middle of one, even when the line is long enough to wrap more than once at sixty columns.

Term  
: A definition list item (not CommonMark).

<div>raw html block</div>

Final line with a very long URL https://example.com/this/is/a/very/long/url/that/cannot/be/wrapped/at/a/space/and/keeps/going/and/going

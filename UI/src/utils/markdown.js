function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function fmtPlain(t) {
  t = esc(t)
  t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
  t = t.replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
  t = t.replace(/_([^_\n]+)_/g, '<em>$1</em>')
  return t
}

function fmtInline(text) {
  const parts = []; let last = 0
  const rx = /`([^`]+)`/g; let m
  while ((m = rx.exec(text)) !== null) {
    if (m.index > last) parts.push(fmtPlain(text.slice(last, m.index)))
    parts.push(`<code>${esc(m[1])}</code>`)
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(fmtPlain(text.slice(last)))
  return parts.join('')
}

function isBox(s) {
  return /─{3,}|━{3,}|═{3,}/.test(s)
}

function parsePipeTbl(lines) {
  if (lines.length < 2) return null
  const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
  if (!/^\|[\s\-:|]+\|/.test(lines[1].trim())) return null
  const hdrs = cells(lines[0])
  const rows = lines.slice(2).filter(l => !l.trim().match(/^\|[\s\-:|]+\|$/))
  let h = `<div class="tw"><table><thead><tr>${hdrs.map(c => `<th>${fmtInline(c)}</th>`).join('')}</tr></thead><tbody>`
  rows.forEach(r => { h += `<tr>${cells(r).map(c => `<td>${fmtInline(c)}</td>`).join('')}</tr>` })
  return h + '</tbody></table></div>'
}

export function renderMD(src) {
  const lines = src.split('\n'), out = []; let i = 0
  while (i < lines.length) {
    const line = lines[i], tr = line.trim()

    if (tr.startsWith('```')) {
      const j_start = i + 1; let j = j_start
      while (j < lines.length && !lines[j].trim().startsWith('```')) j++
      out.push(`<pre><code>${esc(lines.slice(j_start, j).join('\n'))}</code></pre>`)
      i = j + 1; continue
    }

    if (isBox(line)) {
      const blk = []; let k = i
      while (k < lines.length && lines[k].trim() !== '') { blk.push(lines[k]); k++ }
      out.push(`<span class="box-t">${esc(blk.join('\n'))}</span>`)
      i = k; continue
    }

    if (tr.startsWith('|') && i + 1 < lines.length && /^\|[\s\-:|]+\|/.test((lines[i + 1] || '').trim())) {
      const tl = []; let j = i
      while (j < lines.length && lines[j].trim().startsWith('|')) { tl.push(lines[j]); j++ }
      out.push(parsePipeTbl(tl) || `<p>${fmtInline(tl.join(' '))}</p>`)
      i = j; continue
    }

    const hm = tr.match(/^(#{1,4})\s+(.+)$/)
    if (hm) {
      const lv = Math.min(hm[1].length + 1, 4)
      out.push(`<h${lv}>${fmtInline(hm[2].trim())}</h${lv}>`)
      i++; continue
    }

    if (/^(\*{3,}|-{3,}|_{3,})$/.test(tr)) { out.push('<hr>'); i++; continue }

    if (tr.startsWith('> ')) {
      const ql = []; let j = i
      while (j < lines.length && lines[j].trim().startsWith('> ')) { ql.push(lines[j].trim().slice(2)); j++ }
      out.push(`<blockquote><p>${fmtInline(ql.join(' '))}</p></blockquote>`)
      i = j; continue
    }

    if (/^[-*+•]\s/.test(tr)) {
      const items = []; let j = i
      while (j < lines.length && /^[-*+•]\s/.test(lines[j].trim())) {
        items.push(lines[j].trim().replace(/^[-*+•]\s/, '')); j++
      }
      out.push('<ul>' + items.map(x => `<li>${fmtInline(x)}</li>`).join('') + '</ul>')
      i = j; continue
    }

    if (/^\d+[.)]\s/.test(tr) || /^\d+\s+\S/.test(tr)) {
      const items = []; let j = i
      while (j < lines.length) {
        const t2 = lines[j].trim()
        const m2 = t2.match(/^\d+[.)]\s(.+)/) || t2.match(/^\d+\s+(\S.+)/)
        if (m2) { items.push(m2[1]); j++ } else break
      }
      if (items.length) {
        out.push('<ol>' + items.map(x => `<li>${fmtInline(x)}</li>`).join('') + '</ol>')
        i = j; continue
      }
    }

    if (tr === '') { i++; continue }

    const pl = []; let j = i
    while (j < lines.length) {
      const t2 = lines[j].trim()
      if (t2 === '' || /^#{1,4}\s/.test(t2) || t2.startsWith('```') || t2.startsWith('> ') ||
        /^[-*+•]\s/.test(t2) || /^\d+[.)]\s/.test(t2) || /^(\*{3,}|-{3,}|_{3,})$/.test(t2) ||
        t2.startsWith('|') || isBox(t2)) break
      pl.push(lines[j]); j++
    }
    if (pl.length) { out.push(`<p>${fmtInline(pl.join(' '))}</p>`); i = j }
    else i++
  }
  return out.join('\n')
}

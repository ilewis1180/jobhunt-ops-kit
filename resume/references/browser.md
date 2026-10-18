# Driving mdresume from Chrome

The editor keeps everything in IndexedDB, so you can read and write résumé records directly instead of typing into the editor. This is how a résumé corpus is kept in sync with disk.

Use a browser-automation tool that drives the user's real browser profile: the deployment holds their data in that profile's IndexedDB.

Open a résumé: `https://<editor-host>/markdown-resume/edit/<id>`
The résumé list: `https://<editor-host>/markdown-resume/resumes`

Records live under IndexedDB database `localforage`, store `keyvaluepairs`, key `MARKDOWN_RESUME_data`.

## Read

```js
function get(k){return new Promise(r=>{const q=indexedDB.open('localforage');q.onsuccess=()=>{const g=q.result.transaction('keyvaluepairs','readonly').objectStore('keyvaluepairs').get(k);g.onsuccess=()=>r(g.result)}})}
const d = await get('MARKDOWN_RESUME_data');
JSON.stringify(Object.entries(d).map(([id,v])=>({id, name:v.name, md:v.markdown.length, paper:v.styles.paper})), null, 1)
```

## Write

Read the whole object, mutate, put it back. Always report a length or hash so the write can be checked.

```js
const open1=()=>new Promise(r=>{const q=indexedDB.open('localforage');q.onsuccess=()=>r(q.result)});
const db=await open1();
const rd=await new Promise(r=>{const g=db.transaction('keyvaluepairs','readonly').objectStore('keyvaluepairs').get('MARKDOWN_RESUME_data');g.onsuccess=()=>r(g.result)});
rd['<id>'].markdown = /* new content */;
await new Promise(r=>{const p=db.transaction('keyvaluepairs','readwrite').objectStore('keyvaluepairs').put(rd,'MARKDOWN_RESUME_data');p.onsuccess=()=>r(1)});
```

**Reload the page after writing** — the editor holds its own in-memory copy and will not pick up the change otherwise.

### Transferring a whole file

Targeted string replacement is cheap but fragile: a pattern that doesn't match is a silent no-op, and this has twice produced records that differed from disk. For anything beyond a couple of words, send the file wholesale as base64:

```bash
python3 -c "import base64;print(base64.b64encode(open('ATS-Example.md','rb').read()).decode())"
```

```js
rd['<id>'].markdown = new TextDecoder().decode(Uint8Array.from(atob(B64), c=>c.charCodeAt(0)));
```

## Verify

**Hash, don't count bytes.** Two content-loss bugs in this corpus produced coincidentally similar lengths.

```js
const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(rd['<id>'].markdown));
[...new Uint8Array(h)].map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,16)
```

```bash
python3 -c "import hashlib;print(hashlib.sha256(open('ATS-Example.md','rb').read()).hexdigest()[:16])"
```

## Measure the render

Page count:

```js
document.querySelectorAll('.vue-smart-page-break').length + 1
```

Column alignment — every entry should report one distinct left edge and one distinct right edge:

```js
const dls=[...document.querySelectorAll('#vue-smart-pages-preview dl')];
const L=[...new Set(dls.map(d=>Math.round(d.querySelectorAll('dd')[0].getBoundingClientRect().left)))];
const R=[...new Set(dls.map(d=>{const x=d.querySelectorAll('dd')[1];return x?Math.round(x.getBoundingClientRect().right):null}))];
JSON.stringify({rows:dls.length, aligned:L.length===1&&R.length===1, L, R})
```

What a parser sees (the ATS question) — flexbox does not reorder the document, so extraction is sequential:

```js
document.querySelector('#vue-smart-pages-preview').innerText.slice(0, 400)
```

How full the last page is, to judge headroom before switching paper size:

```js
const b=[...document.querySelectorAll('.vue-smart-page-break')];
const prev=document.querySelector('#vue-smart-pages-preview');
const box=e=>{const r=e.getBoundingClientRect();const c=getComputedStyle(e);return r.height+parseFloat(c.marginTop)+parseFloat(c.marginBottom)};
const last=b.length?b[b.length-1].getBoundingClientRect().top:prev.getBoundingClientRect().top;
Math.round([...prev.children].filter(k=>k.getBoundingClientRect().top>=last-2).reduce((s,e)=>s+box(e),0))
```

Ignore the page-break spacer `<div>` in that sum — it is padding, not content.

## Cautions

- Writing to IndexedDB changes the user's data. It is additive and reversible per record, but say so.
- Never set `paper` to anything but `"A4"` or `"letter"`. An invalid key blanks the preview until reverted.
- Changing a setting through the UI does not persist until Save; changing it in IndexedDB persists immediately but needs a reload to show.

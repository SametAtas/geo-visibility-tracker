// Runs the JavaScript of the audit workflow's Code nodes outside n8n, with $input and $() stubbed,
// on the cases shared with the Python and PHP tests. Run: node n8n/test_code_nodes.js
const fs = require('fs');
const path = require('path');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, 'geo_audit_workflow.json'), 'utf8'));
const code = name => wf.nodes.find(n => n.name === name).parameters.jsCode;
const runNode = (name, items, baseUrl) =>
  new Function('$input', '$', code(name))(
    { all: () => items.map(json => ({ json })) },
    () => ({ first: () => ({ json: { base_url: baseUrl } }) }),
  );

const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'tests', 'fixtures', 'signals_cases.json'), 'utf8'));
let failed = 0;
for (const c of fixture.cases) {
  const post = { id: 1, link: '', title: { rendered: '' }, content: { rendered: c.html }, modified_gmt: '2026-01-01T00:00:00' };
  const got = runNode('GEO signals per post', [post], 'https://' + c.own_domain)[0].json;
  const sub = Object.fromEntries(Object.keys(c.expected).map(k => [k, got[k]]));
  const ok = JSON.stringify(sub) === JSON.stringify(c.expected);
  failed += !ok;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name}${ok ? '' : `\n  expected ${JSON.stringify(c.expected)}\n  got      ${JSON.stringify(sub)}`}`);
}

// Summary rounding: 1 of 8 posts = 12.5% must print as 12% (Python rounds halves to even).
const rows = Array.from({ length: 8 }, (_, i) => ({ chars: i, external_sources: i === 0 ? 1 : 0, statistics: 0, quotes: 0,
  has_faq: false, days_since_update: 0, title: `t${i}` }));
const s = runNode('Blog summary', rows, '')[0].json;
if (s.with_any_external_source !== '12%' || s.median_chars !== 4) { failed++; console.log('FAIL summary', s); } else console.log('ok   summary rounding');
console.log(failed ? `${failed} failed` : 'all passed');
process.exit(failed ? 1 : 0);

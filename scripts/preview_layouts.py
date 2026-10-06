"""Renders every layout with sample copy into brand/layouts-preview.html (open in a browser)."""
from pathlib import Path
from brand_layouts import render_post

ROOT = Path(__file__).parent.parent
S = {
 "statement": ("paper", dict(headline="The best AI projects don't start with a *chatbot.*", sub="They start with one broken process and an honest map of the tools around it.")),
 "bignumber": ("ink", dict(number="4x", unit_label="faster lead response", caption="Four disconnected tools started behaving like *one* system.")),
 "beforeafter": ("ink", dict(before="Every business wanted AI in isolation.", after="Intelligence stitched into the tools you already *run.*")),
 "steps": ("sand", dict(headline="One retention *engine,* four moving parts", steps=["Capture", "Qualify", "Follow up", "Retain"])),
 "quote": ("bee", dict(quote="If you can't *measure* it reliably, don't put it in a contract.", attribution="Behind the build")),
 "shards": ("paper", dict(headline="Systems that *scale* without adding headcount")),
 "isostack": ("paper", dict(headline="Intelligence is a *stack,* not a feature", layers=["Your data", "Your tools", "Automation", "Outcomes"])),
 "flow": ("sand", dict(headline="Four tools. One *brain.*", inputs=["WhatsApp", "CRM", "Calendar", "Email"], output="One retention engine")),
 "chat": ("paper", dict(headline="The follow-up nobody *forgets*", messages=[dict(**{"from": "customer"}, text="Can I move my appointment to Friday?"), dict(**{"from": "aelyx"}, text="Done. Friday 4pm is booked. Reminder goes out Thursday."), dict(**{"from": "customer"}, text="Perfect, thanks."), dict(**{"from": "aelyx"}, text="See you Friday.")])),
 "statcards": ("sand", dict(headline="What changed after *go-live*", stats=[dict(value="4x", label="faster lead response"), dict(value="24/7", label="follow-ups, no staff"), dict(value="1", label="system, not four")])),
 "note": ("sand", dict(title="Before you hire, *automate*", items=["Repetitive lead replies", "Appointment reminders", "Follow-up after no-show", "Weekly report to owner"])),
 "poster": ("bee", dict(headline="Automate, don't hire", sub="Aelyx intelligence")),
 "cta": ("ink", dict(headline="Build the *system* once. Let it run.", button="Talk to Aelyx")),
 "marquee": ("ink", dict(word="SYSTEMS", tagline="Growth becomes *predictable* when every lead follows one.")),
}
fonts = (ROOT / "docs/data/fonts.css").read_text()
cards = "".join(f'<figure><div class="p">{render_post(k, f, t, 7).replace("<!--AELYX_FONTS-->", "")}</div><figcaption>{k} · {t}</figcaption></figure>' for k, (t, f) in S.items())
html = f'<!doctype html><meta charset=utf-8><title>Aelyx layouts</title><style>{fonts}body{{margin:24px;background:#fff;font:14px monospace}}.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px}}.p svg{{width:100%;height:auto;display:block;box-shadow:0 0 0 1px #ddd}}</style><div class=g>{cards}</div>'
(ROOT / "brand/layouts-preview.html").write_text(html, encoding="utf-8")
print("ok")

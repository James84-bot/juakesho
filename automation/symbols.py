"""
symbols.py — the Jua Kesho symbol library: one bold illustration per idea, so the picture carries the message.

Every symbol is drawn in a 400x400 box in the brand's sticker style (bright fills, thick usiku outline,
white die-cut edge). The writer chooses one per post from SYMBOLS by meaning; templates render it as the
hero, and base.html.j2 lays a giant faint "ghost" of it behind the glass.

    python symbols.py          # writes exports/symbols-sheet.png to review the whole library
"""
from __future__ import annotations

import json
from pathlib import Path

import brandkit as bk

C = bk.C
O = C["usiku"]           # outline ink
W = 12                   # outline width
S = f'stroke="{O}" stroke-width="{W}" stroke-linejoin="round" stroke-linecap="round"'
HI = 'fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" opacity=".75"'   # highlight sheen


def _hook() -> str:
    return f"""
<path d="M214,34 L214,236 C214,318 104,322 100,246 L100,214 L70,244" fill="none" stroke="{O}" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M214,34 L214,236 C214,318 104,322 100,246 L100,214 L70,244" fill="none" stroke="#D9D4EA" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="214" cy="40" r="22" fill="#D9D4EA" {S}/>
<g transform="rotate(-12 262 250)"><circle cx="262" cy="250" r="72" fill="{C['jua']}" {S}/>
<circle cx="262" cy="250" r="50" fill="none" stroke="{O}" stroke-width="5" opacity=".35"/>
<text x="262" y="266" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="46" fill="{O}">KSh</text></g>
<path d="M226,170 L226,118" {HI}/>"""


def _puppet() -> str:
    phone = f'<rect x="130" y="228" width="140" height="150" rx="24" fill="{C["jacaranda"]}" {S}/>' \
            f'<rect x="148" y="250" width="104" height="96" rx="12" fill="{C["maziwa"]}"/>' \
            f'<text x="200" y="322" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="70" fill="{C["shuka"]}">#</text>'
    return f"""
<g transform="rotate(-8 200 70)">
<rect x="70" y="52" width="260" height="34" rx="14" fill="{C['udongo']}" {S}/>
<rect x="183" y="10" width="34" height="140" rx="14" fill="{C['udongo']}" {S}/></g>
<path d="M92,84 L150,238 M200,150 L200,232 M306,62 L252,238" stroke="{O}" stroke-width="5" fill="none"/>
{phone}"""


def _megaphone() -> str:
    return f"""
<path d="M86,168 L236,86 L236,318 L86,236 Z" fill="{C['shuka']}" {S}/>
<rect x="46" y="160" width="52" height="84" rx="12" fill="{C['jua']}" {S}/>
<path d="M110,236 L130,318 L168,318 L152,254" fill="{C['jua']}" {S}/>
<path d="M280,150 C304,176 304,228 280,254 M318,118 C360,166 360,238 318,286" fill="none" stroke="{O}" stroke-width="14" stroke-linecap="round"/>
<path d="M120,178 L210,130" {HI}/>"""


def _mask() -> str:
    return f"""
<path d="M60,120 C140,90 260,90 340,120 C346,230 290,330 200,352 C110,330 54,230 60,120 Z" fill="{C['maziwa']}" {S}/>
<path d="M104,180 C124,160 160,160 176,184 C156,200 122,202 104,180 Z" fill="{O}"/>
<path d="M224,184 C240,160 276,160 296,180 C278,202 244,200 224,184 Z" fill="{O}"/>
<path d="M150,270 C180,292 220,292 250,270" fill="none" stroke="{O}" stroke-width="12" stroke-linecap="round"/>
<path d="M40,150 L4,130 M360,150 L396,130" stroke="{C['shuka']}" stroke-width="12" stroke-linecap="round"/>
<path d="M200,110 L186,160 L214,200 L196,250" fill="none" stroke="{C['shuka']}" stroke-width="7" stroke-linecap="round"/>"""


def _padlock() -> str:
    return f"""
<path d="M122,176 L122,120 C122,40 278,40 278,120 L278,176" fill="none" stroke="{O}" stroke-width="40" stroke-linecap="round"/>
<path d="M122,176 L122,120 C122,40 278,40 278,120 L278,176" fill="none" stroke="#D9D4EA" stroke-width="20" stroke-linecap="round"/>
<rect x="72" y="166" width="256" height="200" rx="36" fill="{C['jua']}" {S}/>
<circle cx="200" cy="248" r="26" fill="{O}"/><path d="M200,260 L200,318" stroke="{O}" stroke-width="22" stroke-linecap="round"/>
<path d="M100,196 L100,260" {HI}/>"""


def _key() -> str:
    return f"""
<g transform="rotate(-35 200 200)">
<circle cx="110" cy="200" r="78" fill="{C['jua']}" {S}/><circle cx="110" cy="200" r="30" fill="{C['maziwa']}" {S}/>
<rect x="176" y="182" width="200" height="36" rx="10" fill="{C['jua']}" {S}/>
<path d="M300,218 L300,262 L334,262 L334,218 M348,218 L348,248 L372,248 L372,218" fill="{C['jua']}" {S}/>
<path d="M66,160 C80,140 100,132 120,130" {HI}/></g>"""


def _crane() -> str:
    lattice = "".join(f'<path d="M118,{y} L154,{y + 34} M154,{y} L118,{y + 34}" stroke="{O}" stroke-width="5"/>' for y in range(96, 330, 34))
    return f"""
<rect x="118" y="96" width="36" height="270" fill="{C['jua']}" {S}/>{lattice}
<path d="M40,96 L370,96 L370,122 L40,122 Z" fill="{C['jua']}" {S}/>
<path d="M136,96 L136,40 M136,40 L60,96 M136,40 L330,96" stroke="{O}" stroke-width="8" fill="none"/>
<rect x="50" y="122" width="54" height="54" fill="{C['udongo']}" {S}/>
<path d="M318,122 L318,246" stroke="{O}" stroke-width="6"/>
<path d="M318,246 L318,272 C318,290 300,292 296,280" fill="none" stroke="{O}" stroke-width="12" stroke-linecap="round"/>
<path d="M230,366 L230,300 L270,300 L270,260 L330,260 L330,366 Z" fill="{C['maziwa']}" {S}/>
<path d="M60,366 L360,366" stroke="{O}" stroke-width="14" stroke-linecap="round"/>
<g stroke="{O}" stroke-width="3" fill="none" opacity=".75"><path d="M370,122 L336,150 M370,122 L352,166 M370,122 L370,170"/>
<path d="M343,144 C353,150 360,150 368,146 M348,158 C356,162 362,162 369,160"/></g>
<circle cx="206" cy="226" r="44" fill="{C['shuka']}" {S}/><path d="M192,206 L192,246 M220,206 L220,246" stroke="#fff" stroke-width="12" stroke-linecap="round"/>"""


def _half_bridge() -> str:
    return f"""
<path d="M0,300 C80,290 120,316 200,306 C280,296 320,318 400,306 L400,400 L0,400 Z" fill="{C['ziwa']}"/>
<path d="M20,300 L20,180 L150,180 C150,180 158,196 150,214 L60,214 L60,300 Z" fill="{C['udongo']}" {S}/>
<path d="M380,300 L380,180 L276,180 L286,196 L276,214 L340,214 L340,300 Z" fill="{C['udongo']}" {S}/>
<path d="M150,180 L168,172 L162,190 L178,196 L152,214" fill="none" stroke="{O}" stroke-width="6" stroke-linejoin="round"/>
<path d="M20,168 L150,168 M276,168 L380,168" stroke="{C['jua']}" stroke-width="10" stroke-dasharray="18 14"/>
<g transform="translate(96 112)"><path d="M0,56 L20,0 L40,56 Z" fill="{C['shuka']}" {S}/><path d="M9,32 L31,32" stroke="#fff" stroke-width="8"/></g>
<path d="M170,120 L230,120 M178,146 L222,146" stroke="{O}" stroke-width="8" stroke-linecap="round" opacity=".5"/>"""


def _leaky_bucket() -> str:
    coins = "".join(f'<ellipse cx="{x}" cy="{y}" rx="22" ry="12" fill="{C["jua"]}" {S.replace("12", "7", 1)}/>'
                    for x, y in ((96, 300), (150, 348), (306, 330), (262, 372)))
    return f"""
<path d="M92,110 L308,110 L276,300 L124,300 Z" fill="{C['ziwa']}" {S}/>
<ellipse cx="200" cy="110" rx="108" ry="32" fill="{C['jua']}" {S}/>
<ellipse cx="200" cy="106" rx="84" ry="18" fill="{C['udongo']}" opacity=".5"/>
<path d="M130,110 C130,40 270,40 270,110" fill="none" stroke="{O}" stroke-width="10"/>
<circle cx="150" cy="232" r="13" fill="{O}"/><circle cx="238" cy="258" r="13" fill="{O}"/><circle cx="196" cy="200" r="11" fill="{O}"/>
<path d="M150,244 C140,262 120,278 104,288 M238,270 C252,288 280,304 296,318" stroke="{C['jua']}" stroke-width="9" fill="none" stroke-linecap="round"/>
{coins}<path d="M120,150 L136,262" {HI}/>"""


def _sprout() -> str:
    return f"""
<path d="M40,300 C120,270 280,270 360,300 L360,370 L40,370 Z" fill="{C['udongo']}" {S}/>
<path d="M200,300 C200,250 198,200 206,150" fill="none" stroke="{O}" stroke-width="22" stroke-linecap="round"/>
<path d="M200,300 C200,250 198,200 206,150" fill="none" stroke="{C['chai']}" stroke-width="10" stroke-linecap="round"/>
<path d="M204,176 C150,190 96,160 84,96 C150,82 196,120 204,176 Z" fill="{C['chai']}" {S}/>
<path d="M208,150 C236,96 300,70 346,96 C330,150 268,176 208,150 Z" fill="#3FBF6E" {S}/>
<path d="M112,112 C140,120 170,140 190,164" fill="none" stroke="#fff" stroke-width="6" opacity=".6"/>
<circle cx="120" cy="330" r="7" fill="{O}" opacity=".4"/><circle cx="270" cy="340" r="9" fill="{O}" opacity=".4"/>"""


def _ladder() -> str:
    rungs = "".join(f'<path d="M{150 + i * 12},{320 - i * 58} L{250 + i * 12},{320 - i * 58}" stroke="{O}" stroke-width="16" stroke-linecap="round"/>' for i in range(5))
    return f"""
<path d="M130,380 L200,40 M270,380 L320,60" stroke="{O}" stroke-width="30" stroke-linecap="round"/>
<path d="M130,380 L200,40 M270,380 L320,60" stroke="{C['udongo']}" stroke-width="14" stroke-linecap="round"/>{rungs}
<path d="M300,20 L314,58 L354,60 L322,84 L334,122 L300,100 L266,122 L278,84 L246,60 L286,58 Z" fill="{C['jua']}" {S}/>"""


def _rocket() -> str:
    return f"""
<g transform="rotate(35 200 200)">
<path d="M200,26 C258,80 270,170 250,270 L150,270 C130,170 142,80 200,26 Z" fill="{C['maziwa']}" {S}/>
<circle cx="200" cy="140" r="34" fill="{C['ziwa']}" {S}/>
<path d="M150,210 L96,284 L152,270 Z M250,210 L304,284 L248,270 Z" fill="{C['shuka']}" {S}/>
<path d="M164,270 C170,330 186,360 200,388 C214,360 230,330 236,270 Z" fill="{C['jua']}" {S}/>
<path d="M184,272 C190,310 196,330 200,346 C204,330 210,310 216,272 Z" fill="{C['shuka']}"/>
<path d="M170,90 C166,130 164,170 166,220" {HI}/></g>"""


def _bulb() -> str:
    rays = "".join(f'<path d="M{200 + 150 * dx:.0f},{170 + 150 * dy:.0f} L{200 + 186 * dx:.0f},{170 + 186 * dy:.0f}" stroke="{C["jua"]}" stroke-width="14" stroke-linecap="round"/>'
                   for dx, dy in ((-1, 0), (1, 0), (-.71, -.71), (.71, -.71), (0, -1)))
    return f"""{rays}
<path d="M200,54 C272,54 318,108 318,170 C318,222 282,246 268,286 L132,286 C118,246 82,222 82,170 C82,108 128,54 200,54 Z" fill="{C['jua']}" {S}/>
<path d="M170,286 L170,220 C170,196 230,196 230,220 L230,286" fill="none" stroke="{O}" stroke-width="7"/>
<rect x="138" y="286" width="124" height="34" rx="10" fill="#D9D4EA" {S}/><rect x="150" y="320" width="100" height="30" rx="10" fill="#D9D4EA" {S}/>
<path d="M176,354 L224,354" stroke="{O}" stroke-width="16" stroke-linecap="round"/>
<path d="M126,150 C130,118 150,96 176,88" {HI}/>"""


def _robot() -> str:
    return f"""
<path d="M200,76 L200,40" stroke="{O}" stroke-width="10"/><circle cx="200" cy="34" r="20" fill="{C['shuka']}" {S}/>
<rect x="64" y="80" width="272" height="224" rx="60" fill="{C['maziwa']}" {S}/>
<rect x="96" y="120" width="208" height="130" rx="40" fill="{O}"/>
<circle cx="158" cy="178" r="22" fill="{C['pwani']}"/><circle cx="242" cy="178" r="22" fill="{C['pwani']}"/>
<path d="M168,220 C188,236 212,236 232,220" fill="none" stroke="{C['pwani']}" stroke-width="10" stroke-linecap="round"/>
<rect x="30" y="160" width="36" height="72" rx="14" fill="{C['jacaranda']}" {S}/><rect x="334" y="160" width="36" height="72" rx="14" fill="{C['jacaranda']}" {S}/>
<rect x="130" y="304" width="140" height="60" rx="20" fill="{C['jacaranda']}" {S}/>
<path d="M92,120 C100,104 112,96 126,92" {HI}/>"""


def _sunrise() -> str:
    rays = "".join(f'<path d="M{200 + 130 * dx:.0f},{270 + 130 * dy:.0f} L{200 + 186 * dx:.0f},{270 + 186 * dy:.0f}" stroke="{C["jua"]}" stroke-width="16" stroke-linecap="round"/>'
                   for dx, dy in ((-1, 0), (1, 0), (-.87, -.5), (.87, -.5), (-.5, -.87), (.5, -.87), (0, -1)))
    return f"""{rays}
<path d="M90,270 A110,110 0 0 1 310,270 Z" fill="{C['jua']}" {S}/>
<path d="M30,280 L370,280" stroke="{O}" stroke-width="14" stroke-linecap="round"/>
<path d="M60,316 L340,316 M110,350 L290,350" stroke="{C['shuka']}" stroke-width="12" stroke-linecap="round"/>
<path d="M128,236 C140,206 164,186 192,178" {HI}/>"""


def _bridge() -> str:
    return f"""
<path d="M0,318 C100,306 140,330 200,322 C260,314 300,330 400,318 L400,400 L0,400 Z" fill="{C['ziwa']}"/>
<path d="M20,300 L20,180 L380,180 L380,300 L336,300 C330,240 270,210 200,210 C130,210 70,240 64,300 Z" fill="{C['jacaranda']}" {S}/>
<path d="M20,164 L380,164" stroke="{C['jua']}" stroke-width="14" stroke-linecap="round"/>
<path d="M60,164 L60,110 M140,164 L140,110 M260,164 L260,110 M340,164 L340,110" stroke="{O}" stroke-width="8"/>
<path d="M40,112 L360,112" stroke="{O}" stroke-width="10" stroke-linecap="round"/>
<circle cx="110" cy="146" r="12" fill="{C['shuka']}"/><circle cx="290" cy="146" r="12" fill="{C['chai']}"/>"""


def _chain_broken() -> str:
    link = lambda x, rot, col: (f'<g transform="rotate({rot} {x} 200)"><rect x="{x - 90}" y="150" width="180" height="100" rx="50" fill="none" stroke="{O}" stroke-width="44"/>'
                                f'<rect x="{x - 90}" y="150" width="180" height="100" rx="50" fill="none" stroke="{col}" stroke-width="24"/></g>')
    return f"""{link(106, -18, "#D9D4EA")}{link(296, 18, "#D9D4EA")}
<path d="M196,120 L186,158 L206,168 L194,210 M200,250 L212,290" stroke="{C['jua']}" stroke-width="10" stroke-linecap="round" fill="none"/>
<path d="M168,94 L150,70 M232,96 L252,72 M200,86 L200,56" stroke="{C['shuka']}" stroke-width="10" stroke-linecap="round"/>"""


def _hourglass() -> str:
    return f"""
<rect x="90" y="30" width="220" height="36" rx="14" fill="{C['udongo']}" {S}/><rect x="90" y="334" width="220" height="36" rx="14" fill="{C['udongo']}" {S}/>
<path d="M112,66 L288,66 C288,140 222,170 214,200 C222,230 288,260 288,334 L112,334 C112,260 178,230 186,200 C178,170 112,140 112,66 Z" fill="{C['maziwa']}" {S}/>
<path d="M150,116 L250,116 C240,150 212,168 200,192 C188,168 160,150 150,116 Z" fill="{C['jua']}"/>
<path d="M200,200 L200,292" stroke="{C['jua']}" stroke-width="6" stroke-dasharray="6 8"/>
<path d="M132,334 C150,290 250,290 268,334 Z" fill="{C['jua']}"/>
<path d="M130,86 C134,120 150,146 170,164" {HI}/>"""


def _compass() -> str:
    return f"""
<circle cx="200" cy="210" r="160" fill="{C['maziwa']}" {S}/><circle cx="200" cy="210" r="124" fill="none" stroke="{O}" stroke-width="5" opacity=".4"/>
<circle cx="200" cy="40" r="18" fill="{C['jua']}" {S}/>
<path d="M200,98 L234,210 L200,322 L166,210 Z" fill="{C['maziwa']}" {S}/>
<path d="M200,98 L234,210 L166,210 Z" fill="{C['shuka']}" {S}/>
<circle cx="200" cy="210" r="16" fill="{O}"/>
<text x="200" y="138" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="0">N</text>"""


def _eye() -> str:
    return f"""
<path d="M20,200 C90,90 310,90 380,200 C310,310 90,310 20,200 Z" fill="#fff" {S}/>
<circle cx="200" cy="200" r="80" fill="{C['ziwa']}" {S}/><circle cx="200" cy="200" r="38" fill="{O}"/>
<circle cx="222" cy="176" r="16" fill="#fff"/>
<path d="M60,120 L36,86 M130,84 L118,44 M200,72 L200,30 M270,84 L282,44 M340,120 L364,86" stroke="{C['jua']}" stroke-width="12" stroke-linecap="round"/>"""


def _scales() -> str:
    pan = lambda x, y: (f'<path d="M{x},{y - 90} L{x - 56},{y} M{x},{y - 90} L{x + 56},{y}" stroke="{O}" stroke-width="5"/>'
                        f'<path d="M{x - 70},{y} L{x + 70},{y} C{x + 60},{y + 50} {x - 60},{y + 50} {x - 70},{y} Z" fill="{C["jua"]}" {S}/>')
    return f"""
<path d="M200,70 L200,340" stroke="{O}" stroke-width="18" stroke-linecap="round"/>
<path d="M140,350 L260,350" stroke="{O}" stroke-width="22" stroke-linecap="round"/>
<g transform="rotate(-10 200 90)"><path d="M70,90 L330,90" stroke="{C['udongo']}" stroke-width="20" stroke-linecap="round"/>
<path d="M70,90 L330,90" stroke="{O}" stroke-width="4"/>{pan(80, 200)}{pan(320, 200)}</g>
<circle cx="200" cy="70" r="20" fill="{C['jua']}" {S}/>"""


def _magnifier() -> str:
    return f"""
<path d="M250,250 L356,356" stroke="{O}" stroke-width="56" stroke-linecap="round"/>
<path d="M262,262 L350,350" stroke="{C['udongo']}" stroke-width="30" stroke-linecap="round"/>
<circle cx="170" cy="170" r="120" fill="{C['pwani']}" fill-opacity=".35" stroke="{O}" stroke-width="30"/>
<circle cx="170" cy="170" r="120" fill="none" stroke="#D9D4EA" stroke-width="12"/>
<path d="M118,172 L156,210 L228,132" fill="none" stroke="{C['chai']}" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M100,120 C114,98 136,82 160,78" {HI}/>"""


def _shield() -> str:
    return f"""
<path d="M200,30 C260,64 310,70 350,70 C350,220 300,318 200,370 C100,318 50,220 50,70 C90,70 140,64 200,30 Z" fill="{C['chai']}" {S}/>
<path d="M200,70 C246,94 282,100 312,102 C310,214 272,288 200,328 Z" fill="#fff" opacity=".18"/>
<path d="M132,200 L184,252 L276,150" fill="none" stroke="#fff" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M132,200 L184,252 L276,150" fill="none" stroke="{O}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity=".25"/>"""


def _phone_chat() -> str:
    return f"""
<rect x="110" y="40" width="180" height="330" rx="34" fill="{O}" {S}/>
<rect x="126" y="70" width="148" height="264" rx="14" fill="{C['maziwa']}"/>
<rect x="170" y="52" width="60" height="10" rx="5" fill="{C['maziwa']}" opacity=".5"/>
<path d="M140,96 L226,96 C236,96 240,100 240,110 L240,138 C240,148 236,152 226,152 L160,152 L140,168 Z" fill="{C['pwani']}"/>
<path d="M260,184 L178,184 C168,184 164,188 164,198 L164,224 C164,234 168,238 178,238 L244,238 L260,254 Z" fill="{C['jacaranda']}"/>
<path d="M140,272 L214,272 C224,272 228,276 228,286 L228,300 C228,310 224,314 214,314 L156,314 L140,326 Z" fill="{C['pwani']}"/>
<path d="M300,86 C330,96 348,120 352,150 M306,40 C354,54 384,96 388,146" stroke="{C['jua']}" stroke-width="12" fill="none" stroke-linecap="round"/>"""


def _matatu() -> str:
    return f"""
<path d="M40,290 L40,150 C40,122 60,104 88,104 L320,104 C344,104 360,120 366,146 L380,236 L380,290 Z" fill="{C['jua']}" {S}/>
<path d="M40,226 L380,226" stroke="{C['shuka']}" stroke-width="22"/><path d="M40,252 L380,252" stroke="{C['jacaranda']}" stroke-width="12"/>
<rect x="64" y="126" width="62" height="62" rx="10" fill="{C['ziwa']}" {S.replace('12', '7', 1)}/>
<rect x="140" y="126" width="62" height="62" rx="10" fill="{C['ziwa']}" {S.replace('12', '7', 1)}/>
<rect x="216" y="126" width="62" height="62" rx="10" fill="{C['ziwa']}" {S.replace('12', '7', 1)}/>
<path d="M294,126 L334,126 C344,126 348,132 350,142 L358,188 L294,188 Z" fill="{C['ziwa']}" stroke="{O}" stroke-width="7" stroke-linejoin="round"/>
<circle cx="112" cy="296" r="40" fill="{O}"/><circle cx="112" cy="296" r="16" fill="#D9D4EA"/>
<circle cx="310" cy="296" r="40" fill="{O}"/><circle cx="310" cy="296" r="16" fill="#D9D4EA"/>
<rect x="150" y="70" width="110" height="34" rx="8" fill="{C['chai']}" {S.replace('12', '7', 1)}/>
<text x="205" y="96" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="24" fill="#fff">46</text>
<path d="M70,280 L20,280" stroke="{O}" stroke-width="10" stroke-linecap="round"/>"""


def _grad_cap() -> str:
    return f"""
<path d="M120,190 L120,280 C120,320 280,320 280,280 L280,190" fill="{O}" {S}/>
<path d="M20,160 L200,80 L380,160 L200,240 Z" fill="{C['jacaranda']}" {S}/>
<path d="M200,160 L330,190 L330,290" fill="none" stroke="{C['jua']}" stroke-width="10" stroke-linecap="round"/>
<path d="M318,286 L342,286 L350,340 L310,340 Z" fill="{C['jua']}" {S.replace('12', '7', 1)}/>
<circle cx="200" cy="160" r="14" fill="{C['jua']}"/>"""


def _music() -> str:
    return f"""
<path d="M70,240 C70,110 130,50 200,50 C270,50 330,110 330,240" fill="none" stroke="{O}" stroke-width="30" stroke-linecap="round"/>
<path d="M70,240 C70,110 130,50 200,50 C270,50 330,110 330,240" fill="none" stroke="{C['jacaranda']}" stroke-width="14" stroke-linecap="round"/>
<rect x="42" y="220" width="80" height="130" rx="30" fill="{C['shuka']}" {S}/><rect x="278" y="220" width="80" height="130" rx="30" fill="{C['shuka']}" {S}/>
<path d="M186,300 L186,170 L250,150 L250,270" fill="none" stroke="{O}" stroke-width="12" stroke-linejoin="round"/>
<ellipse cx="172" cy="302" rx="24" ry="18" fill="{C['jua']}" {S.replace('12', '7', 1)}/><ellipse cx="236" cy="272" rx="24" ry="18" fill="{C['jua']}" {S.replace('12', '7', 1)}/>"""


def _coins_up() -> str:
    stack = "".join(f'<ellipse cx="{x}" cy="{y}" rx="56" ry="20" fill="{C["jua"]}" {S.replace("12", "8", 1)}/>'
                    for x, stackh in ((110, 3), (210, 5), (310, 7)) for y in range(340, 340 - stackh * 30, -30))
    return f"""{stack}
<path d="M60,210 L160,150 L230,176 L330,70" fill="none" stroke="{O}" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M60,210 L160,150 L230,176 L330,70" fill="none" stroke="{C['chai']}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M280,64 L340,60 L336,120" fill="none" stroke="{O}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>"""


def _warning() -> str:
    return f"""
<path d="M200,40 L368,340 C372,352 366,360 354,360 L46,360 C34,360 28,352 32,340 Z" fill="{C['jua']}" {S}/>
<path d="M200,130 L200,250" stroke="{O}" stroke-width="30" stroke-linecap="round"/><circle cx="200" cy="308" r="20" fill="{O}"/>
<path d="M150,120 L110,196" {HI}/>"""


def _unity() -> str:
    people = "".join(bk.stick(who, x, 372, "cheer", "happy", 1.3) for who, x in (("student", 86), ("mama_mboga", 200), ("techie", 314)))
    return f'<g>{people}</g><path d="M36,378 L364,378" stroke="{O}" stroke-width="10" stroke-linecap="round"/>'


def _target() -> str:
    return f"""
<circle cx="180" cy="220" r="150" fill="#fff" {S}/><circle cx="180" cy="220" r="104" fill="{C['shuka']}" {S.replace('12', '6', 1)}/>
<circle cx="180" cy="220" r="60" fill="#fff" {S.replace('12', '6', 1)}/><circle cx="180" cy="220" r="24" fill="{C['shuka']}"/>
<path d="M186,214 L350,50" stroke="{O}" stroke-width="16" stroke-linecap="round"/>
<path d="M330,40 L370,30 L360,70 Z M350,60 L390,50 L380,90 Z" fill="{C['jua']}" {S.replace('12', '6', 1)}/>"""


def _signal() -> str:
    bars = "".join(f'<rect x="{60 + i * 72}" y="{330 - (i + 1) * 60}" width="50" height="{(i + 1) * 60}" rx="10" fill="{c}" {S}/>'
                   for i, c in enumerate((C["pwani"], C["ziwa"], C["jacaranda"], C["jua"])))
    return f"""{bars}<path d="M40,350 L360,350" stroke="{O}" stroke-width="12" stroke-linecap="round"/>
<path d="M286,40 C316,50 334,70 344,100 M300,6 C346,22 374,56 384,104" stroke="{C['chai']}" stroke-width="12" fill="none" stroke-linecap="round"/>"""


def _brain() -> str:
    return f"""
<path d="M200,70 C160,40 96,56 90,106 C50,116 38,170 66,198 C40,236 64,290 110,294 C124,338 180,352 200,320 Z" fill="{C['waridi']}" {S}/>
<path d="M200,70 C240,40 304,56 310,106 C350,116 362,170 334,198 C360,236 336,290 290,294 C276,338 220,352 200,320 Z" fill="{C['waridi']}" {S}/>
<path d="M200,70 L200,320" stroke="{O}" stroke-width="8"/>
<path d="M130,130 C150,150 150,176 128,196 M140,244 C170,236 180,262 170,284" stroke="{O}" stroke-width="7" fill="none" stroke-linecap="round"/>
<path d="M240,140 L290,140 L290,190 L330,190 M240,240 L270,240 L270,270 L310,270" stroke="{C['pwani']}" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="330" cy="190" r="12" fill="{C['pwani']}" {S.replace('12', '5', 1)}/><circle cx="310" cy="270" r="12" fill="{C['pwani']}" {S.replace('12', '5', 1)}/>"""


# name: (draw, meaning shown to the writer)
SYMBOLS = {
    "hook": (_hook, "scams, bait, 'too good to be true' offers, phishing"),
    "puppet": (_puppet, "manipulation: paid bloggers, bot armies, goons for hire, someone else pulling the strings"),
    "megaphone": (_megaphone, "noise, propaganda, amplifying a voice, speaking up"),
    "mask": (_mask, "fakes: deepfakes, fake accounts, pretending, hidden identity"),
    "padlock": (_padlock, "privacy, security, protecting accounts and data"),
    "key": (_key, "unlocking: a skill, a prompt, access, the answer"),
    "crane": (_crane, "stalled projects, construction that stopped, work on pause"),
    "half_bridge": (_half_bridge, "unfinished promises, projects that never connect, gaps"),
    "leaky_bucket": (_leaky_bucket, "money leaking away: misused public funds, waste, hidden costs"),
    "sprout": (_sprout, "growth, starting small, patience, learning"),
    "ladder": (_ladder, "opportunity, careers, climbing step by step"),
    "rocket": (_rocket, "launching, speed, going big, startups"),
    "bulb": (_bulb, "an idea, a hack, 'aha', creativity"),
    "robot": (_robot, "AI as a helper or agent, automation"),
    "brain": (_brain, "thinking, learning, how AI 'thinks', knowledge"),
    "sunrise": (_sunrise, "kesho: the future arriving, hope, a new start"),
    "bridge": (_bridge, "connection: Africa to the world, people to opportunity"),
    "chain_broken": (_chain_broken, "breaking free: from old ways, from being used, freedom"),
    "hourglass": (_hourglass, "time running out, waiting too long, 'Africa can't wait'"),
    "compass": (_compass, "direction, choosing a path, guidance"),
    "eye": (_eye, "seeing clearly, awareness, 'see through it', watching"),
    "scales": (_scales, "fairness, justice, weighing both sides, accountability"),
    "magnifier": (_magnifier, "checking facts, verifying sources, looking closer"),
    "shield": (_shield, "protection, staying safe, trust"),
    "phone_chat": (_phone_chat, "DMs, WhatsApp, messages, online conversations"),
    "matatu": (_matatu, "everyday Kenyan life, the hustle, getting there together"),
    "grad_cap": (_grad_cap, "campus, exams, education, graduates"),
    "music": (_music, "music, artists, sound, the creative industry"),
    "coins_up": (_coins_up, "earning, growth in money, side income done right"),
    "warning": (_warning, "alert, caution, danger ahead"),
    "unity": (_unity, "unity across tribes and classes, supporting our own, community"),
    "target": (_target, "a goal, focus, hitting the mark"),
    "signal": (_signal, "connectivity, internet access, being online"),
}

CUT_FILTER = (f'<filter id="symcut" x="-12%" y="-12%" width="124%" height="124%">'
              f'<feMorphology in="SourceAlpha" operator="dilate" radius="9" result="d"/>'
              f'<feFlood flood-color="#ffffff"/><feComposite in2="d" operator="in" result="w"/>'
              f'<feDropShadow in="w" dx="6" dy="10" stdDeviation="6" flood-color="{O}" flood-opacity=".35" result="ws"/>'
              f'<feMerge><feMergeNode in="ws"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def portrait(uri: str, seed: int = 7) -> str:
    """A real photo of someone we celebrate, in full colour inside an organic brand frame (viewBox 0 0 400 400)."""
    shape = bk.blob_path(200, 200, 176, seed, wobble=0.10, points=8)
    ring = bk.blob_path(200, 200, 192, seed + 3, wobble=0.08, points=9)
    return (f'<defs><clipPath id="pclip"><path d="{shape}"/></clipPath></defs>'
            f'<path d="{ring}" fill="none" stroke="{C["jua"]}" stroke-width="10" stroke-dasharray="2 18" stroke-linecap="round"/>'
            f'<g filter="url(#symcut)"><defs>{CUT_FILTER}</defs>'
            f'<path d="{shape}" fill="{C["maziwa"]}"/>'
            f'<image href="{uri}" x="16" y="16" width="368" height="368" preserveAspectRatio="xMidYMid slice" clip-path="url(#pclip)"/>'
            f'<path d="{shape}" fill="none" stroke="{O}" stroke-width="8"/></g>'
            f'<g transform="translate(318 44) rotate(12)"><path d="M0,-30 L8,-8 L30,0 L8,8 L0,30 L-8,8 L-30,0 L-8,-8 Z" fill="{C["jua"]}" {S.replace("12", "5", 1)}/></g>')


def names() -> list[str]:
    return list(SYMBOLS)


def menu() -> str:
    """The list the writer chooses from."""
    return "\n".join(f"- {k}: {v[1]}" for k, v in SYMBOLS.items())


def art(name: str) -> str:
    """Sticker version: inner SVG for a viewBox="0 0 400 400" element."""
    draw = SYMBOLS[name][0]
    return f'<defs>{CUT_FILTER}</defs><g filter="url(#symcut)">{draw()}</g>'


def ghost(name: str, color: str = "#ffffff") -> str:
    """Flat silhouette for the giant background version (no outline detail, one colour)."""
    draw = SYMBOLS[name][0]
    return (f'<defs><filter id="symghost"><feFlood flood-color="{color}"/>'
            f'<feComposite in2="SourceAlpha" operator="in"/></filter></defs><g filter="url(#symghost)">{draw()}</g>')


def sheet(out: Path) -> Path:
    from playwright.sync_api import sync_playwright

    cells = "".join(f'<figure><svg viewBox="-20 -20 440 440">{art(n)}</svg><figcaption>{n}</figcaption></figure>' for n in SYMBOLS)
    html = (f'<html><head><meta charset="utf-8"><style>{bk.font_faces((Path(__file__).parent.parent / "assets" / "fonts").as_uri())}'
            f'body{{margin:0;background:{C["jacaranda"]};font:700 22px Unbounded;color:#fff}}'
            f'main{{display:grid;grid-template-columns:repeat(6,300px);gap:24px;padding:30px}}'
            f'figure{{margin:0;text-align:center}}svg{{width:300px;height:300px}}</style></head><body><main>{cells}</main></body></html>')
    tmp = out.with_suffix(".html")
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1980, "height": 400})
        pg.goto(tmp.as_uri())
        pg.evaluate("document.fonts.ready")
        pg.screenshot(path=str(out), full_page=True)
        b.close()
    tmp.unlink()
    return out


if __name__ == "__main__":
    print(sheet(Path(__file__).resolve().parent.parent / "exports" / "symbols-sheet.png"))

"""presenter_art.py — the Kenya on Record presenter, drawn in code (SVG, 600x760 bust).

An original illustrated character: short twists, a thrifted 90s print shirt over a black tee, two silver chains.
Every part is a separate layer so presenter.py can animate him for free:
  BASE            body, head, hair (never changes)
  MOUTHS[A..H, X] Rhubarb Lip Sync mouth shapes (+ SMILE for the opening and closing)
  EYES[open|half|closed]   for blinks
  BROWS[calm|raised|serious]
All layers share one viewBox, so stacking them in order gives the full face.
"""
import math
SK, SKD, SKL = "#6B4126", "#55311B", "#80502F"
HAIR, HAIRL = "#17100B", "#2B1E15"
# --- twists: short coils packed over the crown (sponge-twist style), back rows first
import random
_rng = random.Random(7)
tw = []
for (rx, ry, n, r) in [(86, 92, 19, 13), (74, 80, 16, 13), (58, 64, 12, 12), (38, 40, 7, 12)]:
    for i in range(n):
        a = math.radians(192 + i * (156 / (n - 1)))
        cx, cy = 300 + rx * math.cos(a), (236 if rx > 50 else 222) + ry * math.sin(a) * 0.95
        rr = r + _rng.uniform(-1.5, 1.5)
        tw.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" fill="{HAIR}"/>'
                  f'<path d="M{cx-rr*0.55:.1f} {cy-rr*0.2:.1f} Q{cx:.1f} {cy-rr*0.75:.1f} {cx+rr*0.55:.1f} {cy-rr*0.2:.1f}" stroke="{HAIRL}" stroke-width="3" fill="none" stroke-linecap="round"/>')
twists = "\n".join(tw)

BASE = f'''<svg viewBox="0 0 600 760" width="100%" height="100%" preserveAspectRatio="xMidYMax meet" aria-hidden="true" style="position:absolute;inset:0">
<defs>
<clipPath id="shirtClip"><path d="M40 760 C52 650 140 598 232 576 L368 576 C460 598 548 650 560 760 Z"/></clipPath>
</defs>
<!-- shirt: vintage 90s print, big muted shapes -->
<path d="M40 760 C52 650 140 598 232 576 L368 576 C460 598 548 650 560 760 Z" fill="#6A4E3C"/>
<g clip-path="url(#shirtClip)">
<path d="M40 640 C120 600 170 660 150 720 C130 770 60 760 40 740 Z" fill="#3E7470"/>
<path d="M430 600 C500 610 560 660 540 720 C500 700 440 690 420 650 Z" fill="#3E7470"/>
<path d="M120 760 C150 700 210 690 230 740 L230 760 Z" fill="#C9B48F" opacity=".75"/>
<path d="M380 760 C400 720 460 700 500 760 Z" fill="#C9B48F" opacity=".75"/>
<path d="M150 600 L215 585 L200 640 Z" fill="#8A6A52"/>
<path d="M455 640 L520 690 L470 700 Z" fill="#8A6A52"/>
<path d="M60 700 C100 690 120 720 110 760" stroke="#C9B48F" stroke-width="10" fill="none" opacity=".6"/>
</g>
<!-- shoulder shading -->
<path d="M40 760 C52 650 140 598 232 576 L250 600 C170 630 110 690 96 760 Z" fill="#000" opacity=".12"/>
<path d="M560 760 C548 650 460 598 368 576 L350 600 C430 630 490 690 504 760 Z" fill="#000" opacity=".12"/>
<!-- black tee between the open shirt -->
<path d="M236 580 C252 640 262 700 258 760 L342 760 C338 700 348 640 364 580 Z" fill="#141414"/>
<path d="M248 586 C272 616 328 616 352 586" stroke="#262626" stroke-width="7" fill="none"/>
<!-- neck -->
<path d="M250 470 L350 470 L352 596 C326 616 274 616 248 596 Z" fill="{SK}"/>
<path d="M252 470 L348 470 L350 530 C322 546 278 546 250 530 Z" fill="{SKD}"/>
<!-- open camp collar -->
<path d="M236 572 L192 606 L246 690 L262 618 Z" fill="#7A5B47"/>
<path d="M364 572 L408 606 L354 690 L338 618 Z" fill="#7A5B47"/>
<path d="M236 572 L262 618 L246 690" stroke="#4E392B" stroke-width="2" fill="none"/>
<path d="M364 572 L338 618 L354 690" stroke="#4E392B" stroke-width="2" fill="none"/>
<!-- layered silver chains: the signature -->
<path d="M262 592 C278 634 322 634 338 592" stroke="#D9DDE2" stroke-width="3.5" fill="none" stroke-dasharray="5 2"/>
<path d="M256 598 C272 664 328 664 344 598" stroke="#C3C8CE" stroke-width="3" fill="none" stroke-dasharray="4 2"/>
<g transform="translate(0 35) translate(300 470) scale(1.22) translate(-300 -470)">
<!-- ears -->
<ellipse cx="217" cy="318" rx="15" ry="27" fill="{SKD}"/>
<ellipse cx="383" cy="318" rx="15" ry="27" fill="{SKD}"/>
<ellipse cx="219" cy="318" rx="7" ry="15" fill="#47291A"/>
<ellipse cx="381" cy="318" rx="7" ry="15" fill="#47291A"/>
<!-- head -->
<path d="M220 292 C220 212 260 174 300 174 C340 174 380 212 380 292 C380 376 354 438 300 466 C246 438 220 376 220 292 Z" fill="{SK}"/>
<path d="M220 292 C220 376 246 438 300 466 C262 436 236 380 234 300 C234 250 250 214 272 192 C240 206 220 246 220 292 Z" fill="{SKD}" opacity=".45"/>
<path d="M300 466 C262 444 240 402 232 352 C252 400 276 428 300 436 C324 428 348 400 368 352 C360 402 338 444 300 466 Z" fill="{SKD}" opacity=".7"/>
<ellipse cx="262" cy="352" rx="22" ry="14" fill="{SKL}" opacity=".35"/>
<ellipse cx="338" cy="352" rx="22" ry="14" fill="{SKL}" opacity=".35"/>
<!-- light beard line and moustache -->
<path d="M262 420 C280 448 320 448 338 420 C330 456 270 456 262 420 Z" fill="{HAIR}" opacity=".55"/>
<path d="M274 388 C288 380 312 380 326 388 C312 386 288 386 274 388 Z" fill="{HAIR}" opacity=".75"/>
<!-- nose -->
<path d="M292 300 C290 330 284 346 280 356 C292 366 308 366 320 356 C316 346 310 330 308 300" fill="{SKD}" opacity=".55"/>
<ellipse cx="288" cy="356" rx="7" ry="4" fill="#3A2013"/>
<ellipse cx="312" cy="356" rx="7" ry="4" fill="#3A2013"/>
<!-- hair: short twists -->
<path d="M220 292 C210 196 256 150 300 150 C344 150 390 196 380 294 C372 252 348 230 300 228 C252 230 228 252 220 292 Z" fill="{HAIR}"/>
{twists}
</g>
</svg>'''

HEAD_T = 'transform="translate(0 35) translate(300 470) scale(1.22) translate(-300 -470)"'
def svg(inner):
    return f'<svg viewBox="0 0 600 760" width="100%" height="100%" preserveAspectRatio="xMidYMax meet" aria-hidden="true" style="position:absolute;inset:0"><g {HEAD_T}>{inner}</g></svg>'

LIP, LIPD, DARK, TEETH, TONGUE = "#7A4030", "#5A2C1F", "#2A120C", "#F3EEE6", "#B25A50"
mouths = {
 "X": f'<path d="M276 410 Q300 416 324 410" stroke="{LIPD}" stroke-width="5" stroke-linecap="round" fill="none"/><path d="M280 414 Q300 426 320 414 Q300 420 280 414 Z" fill="{LIP}"/>',
 "A": f'<path d="M272 408 Q300 402 328 408 Q300 424 272 408 Z" fill="{LIP}"/><path d="M274 409 Q300 412 326 409" stroke="{LIPD}" stroke-width="4" stroke-linecap="round" fill="none"/>',
 "B": f'<path d="M274 404 Q300 398 326 404 Q322 420 300 422 Q278 420 274 404 Z" fill="{DARK}"/><path d="M280 405 Q300 401 320 405 L319 411 Q300 409 281 411 Z" fill="{TEETH}"/><path d="M280 416 Q300 420 320 416 L318 413 Q300 416 282 413 Z" fill="{TEETH}"/><path d="M272 404 Q300 396 328 404 Q322 428 300 430 Q278 428 272 404 Z M274 404 Q278 420 300 422 Q322 420 326 404 Q300 398 274 404 Z" fill="{LIP}" fill-rule="evenodd"/>',
 "C": f'<path d="M272 400 Q300 392 328 400 Q324 430 300 434 Q276 430 272 400 Z" fill="{DARK}"/><path d="M280 401 Q300 396 320 401 L319 408 Q300 405 281 408 Z" fill="{TEETH}"/><path d="M284 428 Q300 418 316 428 Q300 433 284 428 Z" fill="{TONGUE}"/><path d="M268 400 Q300 388 332 400 Q326 440 300 442 Q274 440 268 400 Z M272 400 Q276 430 300 434 Q324 430 328 400 Q300 392 272 400 Z" fill="{LIP}" fill-rule="evenodd"/>',
 "D": f'<path d="M268 398 Q300 388 332 398 Q328 444 300 450 Q272 444 268 398 Z" fill="{DARK}"/><path d="M278 399 Q300 393 322 399 L321 407 Q300 403 279 407 Z" fill="{TEETH}"/><path d="M282 442 Q300 428 318 442 Q300 449 282 442 Z" fill="{TONGUE}"/><path d="M264 398 Q300 384 336 398 Q330 454 300 458 Q270 454 264 398 Z M268 398 Q272 444 300 450 Q328 444 332 398 Q300 388 268 398 Z" fill="{LIP}" fill-rule="evenodd"/>',
 "E": f'<ellipse cx="300" cy="414" rx="15" ry="17" fill="{DARK}"/><ellipse cx="300" cy="414" rx="15" ry="17" fill="none" stroke="{LIP}" stroke-width="9"/>',
 "F": f'<ellipse cx="300" cy="414" rx="8" ry="8" fill="{DARK}"/><ellipse cx="300" cy="414" rx="10" ry="10" fill="none" stroke="{LIP}" stroke-width="11"/>',
 "G": f'<path d="M276 406 Q300 400 324 406 L322 414 Q300 412 278 414 Z" fill="{TEETH}"/><path d="M274 406 Q300 398 326 406" stroke="{LIP}" stroke-width="6" stroke-linecap="round" fill="none"/><path d="M278 414 Q300 410 322 414 Q300 428 278 414 Z" fill="{LIP}"/>',
 "H": f'<path d="M272 400 Q300 392 328 400 Q324 430 300 434 Q276 430 272 400 Z" fill="{DARK}"/><path d="M280 401 Q300 396 320 401 L319 408 Q300 405 281 408 Z" fill="{TEETH}"/><path d="M286 430 Q292 410 300 408 Q308 410 314 430 Q300 434 286 430 Z" fill="{TONGUE}"/><path d="M268 400 Q300 388 332 400 Q326 440 300 442 Q274 440 268 400 Z M272 400 Q276 430 300 434 Q324 430 328 400 Q300 392 272 400 Z" fill="{LIP}" fill-rule="evenodd"/>',
 "SMILE": f'<path d="M272 406 Q300 426 328 406 Q300 418 272 406 Z" fill="{LIP}"/><path d="M272 406 Q300 420 328 406" stroke="{LIPD}" stroke-width="4" stroke-linecap="round" fill="none"/>',
}
EYE = "#F1ECE4"
eyes = {
 "open": f'<path d="M248 306 Q266 292 286 306 Q266 316 248 306 Z" fill="{EYE}"/><circle cx="267" cy="305" r="8" fill="#2A170D"/><circle cx="270" cy="302" r="2.4" fill="#fff"/><path d="M314 306 Q334 292 352 306 Q334 316 314 306 Z" fill="{EYE}"/><circle cx="333" cy="305" r="8" fill="#2A170D"/><circle cx="336" cy="302" r="2.4" fill="#fff"/><path d="M246 305 Q266 290 288 305" stroke="#1A0F09" stroke-width="3.5" fill="none" stroke-linecap="round"/><path d="M312 305 Q334 290 354 305" stroke="#1A0F09" stroke-width="3.5" fill="none" stroke-linecap="round"/>',
 "half": f'<path d="M248 306 Q266 300 286 306 Q266 314 248 306 Z" fill="{EYE}"/><circle cx="267" cy="307" r="6" fill="#2A170D"/><path d="M314 306 Q334 300 352 306 Q334 314 314 306 Z" fill="{EYE}"/><circle cx="333" cy="307" r="6" fill="#2A170D"/><path d="M246 305 Q266 298 288 305" stroke="#1A0F09" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M312 305 Q334 298 354 305" stroke="#1A0F09" stroke-width="4" fill="none" stroke-linecap="round"/>',
 "closed": '<path d="M248 308 Q266 316 286 308" stroke="#1A0F09" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M314 308 Q334 316 352 308" stroke="#1A0F09" stroke-width="4" fill="none" stroke-linecap="round"/>',
}
brows = {
 "calm": '<path d="M244 280 Q266 268 290 276" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/><path d="M310 276 Q334 268 356 280" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/>',
 "raised": '<path d="M244 270 Q266 254 290 264" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/><path d="M310 264 Q334 254 356 270" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/>',
 "serious": '<path d="M244 276 Q268 272 292 284" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/><path d="M308 284 Q332 272 356 276" stroke="#140C08" stroke-width="9" stroke-linecap="round" fill="none"/>',
}

MOUTHS = {k: svg(v) for k, v in mouths.items()}
EYES = {k: svg(v) for k, v in eyes.items()}
BROWS = {k: svg(v) for k, v in brows.items()}
SHAPES = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]   # Rhubarb's basic + extended shapes

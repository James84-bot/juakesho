// mtaa_rig.js — Mtaa Mode's cast, drawn and animated in the page (SVG). One rig for everyone: a torso, a head that
// tilts, and arms and legs solved by two-bone IK from where the hands and feet should be, so a pose is just "hand
// here, foot there". Every character is drawn facing right; facing left is a mirror. Deterministic: the same time
// always draws the same frame (video.py steps it frame by frame).
const NS = "http://www.w3.org/2000/svg";
const RIG = { hipY: -232, hipX: 24, shY: -418, shX: 56, upper: 96, fore: 92, thigh: 106, shin: 106, ankle: 22,
              neckY: -438, headY: -548, headRx: 64, headRy: 72, headScale: 1.24 };   // a big head reads on a phone

function el(tag, attrs, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

// Two-bone IK: the elbow (or knee) for a joint at S reaching T, bending to the side `bend` (+1 / -1).
function ik(S, T, a, b, bend) {
  let dx = T[0] - S[0], dy = T[1] - S[1];
  let d = Math.hypot(dx, dy);
  const max = a + b - 0.5, min = Math.abs(a - b) + 0.5;
  if (d > max) { dx *= max / d; dy *= max / d; d = max; }
  if (d < min) { dx *= min / (d || 1); dy *= min / (d || 1); d = min; }
  const base = Math.atan2(dy, dx);
  const off = Math.acos(Math.min(1, Math.max(-1, (a * a + d * d - b * b) / (2 * a * d))));
  const ang = base + bend * off;
  return { E: [S[0] + Math.cos(ang) * a, S[1] + Math.sin(ang) * a], T: [S[0] + dx, S[1] + dy] };
}

const lerp = (a, b, k) => a + (b - a) * k;
const smooth = (k) => k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k);

// ---------------------------------------------------------------------------------------------------------------
// Drawing a character: returns the parts the animator moves
// ---------------------------------------------------------------------------------------------------------------
function drawCharacter(parent, c) {
  const root = el("g", {}, parent);            // world position (translate) and facing (mirror)
  const body = el("g", {}, root);              // breathing, bounce, lean
  const shadow = el("ellipse", { cx: 0, cy: 6, rx: 92, ry: 16, fill: "rgba(0,0,0,.28)" }, root);
  root.insertBefore(shadow, body);
  const P = {};
  const limb = (color, w, g) => el("path", { fill: "none", stroke: color, "stroke-width": w, "stroke-linecap": "round",
                                            "stroke-linejoin": "round" }, g);
  // back arm (behind the body)
  P.backArm = el("g", {}, body);
  P.backUpper = limb(c.sleeve, 34, P.backArm);
  P.backFore = limb(c.forearm, 30, P.backArm);
  P.backHand = el("circle", { r: 17, fill: c.skin }, P.backArm);
  if (c.prop === "book") {   // the landlord's rent book, in the back hand
    P.book = el("g", {}, P.backArm);
    el("rect", { x: -26, y: -8, width: 52, height: 64, rx: 6, fill: "#7A2E2E" }, P.book);
    el("rect", { x: -20, y: -2, width: 40, height: 6, rx: 2, fill: "#E9D9B0" }, P.book);
  }
  // legs and shoes
  P.legs = el("g", {}, body);
  P.legB = limb(c.pants, c.legW || 44, P.legs);
  P.legF = limb(c.pants, c.legW || 44, P.legs);
  P.shoeB = el("path", { fill: c.shoe }, P.legs);
  P.shoeF = el("path", { fill: c.shoe }, P.legs);
  // torso
  P.torso = el("g", {}, body);
  drawTop(P.torso, c);
  // head
  P.head = el("g", {}, body);
  el("rect", { x: -17, y: RIG.neckY - 26, width: 34, height: 44, rx: 12, fill: c.skin }, P.head);
  const H = el("g", { transform: `translate(0 ${RIG.headY}) scale(${RIG.headScale})` }, P.head);
  P.H = H;
  drawHairBack(H, c);
  el("ellipse", { cx: -58, cy: 6, rx: 13, ry: 16, fill: c.skin }, H);                              // ear
  el("ellipse", { cx: -58, cy: 6, rx: 6, ry: 8, fill: "rgba(0,0,0,.18)" }, H);
  el("ellipse", { cx: 0, cy: 0, rx: RIG.headRx, ry: RIG.headRy, fill: c.skin }, H);                 // head
  el("ellipse", { cx: 30, cy: 18, rx: 14, ry: 9, fill: "rgba(255,90,90,.10)" }, H);                 // cheek
  const F = el("g", {}, H);                                                                         // face (3/4 to the right)
  P.eyes = el("g", {}, F);
  P.eyeL = el("g", { transform: "translate(-6 -4)" }, P.eyes);
  P.eyeR = el("g", { transform: "translate(32 -4)" }, P.eyes);
  for (const e of [P.eyeL, P.eyeR]) {
    e.white = el("ellipse", { cx: 0, cy: 0, rx: 12, ry: 14, fill: "#FFFFFF" }, e);
    e.pupil = el("circle", { cx: 3, cy: 1, r: 7, fill: "#1A1412" }, e);
    el("circle", { cx: 5.5, cy: -2, r: 2.2, fill: "#FFFFFF" }, e);
    e.lid = el("rect", { x: -14, y: -16, width: 28, height: 0, fill: c.skin }, e);                 // blink and narrow
  }
  P.browL = el("path", { fill: "none", stroke: c.brow || "#1A1412", "stroke-width": 6, "stroke-linecap": "round" }, F);
  P.browR = el("path", { fill: "none", stroke: c.brow || "#1A1412", "stroke-width": 6, "stroke-linecap": "round" }, F);
  el("path", { d: "M17,8 Q26,22 16,24", fill: "none", stroke: "rgba(0,0,0,.35)", "stroke-width": 4, "stroke-linecap": "round" }, F);
  P.mouth = el("path", { fill: "#3A1512", stroke: "#3A1512", "stroke-width": 4, "stroke-linejoin": "round" }, F);
  if (c.mustache) el("path", { d: "M2,30 Q14,22 26,26 Q36,22 44,30 Q32,34 23,31 Q12,35 2,30Z", fill: c.mustache }, F);
  if (c.glasses) {
    el("circle", { cx: -6, cy: -4, r: 17, fill: "none", stroke: "#2B2B2B", "stroke-width": 4 }, F);
    el("circle", { cx: 32, cy: -4, r: 17, fill: "none", stroke: "#2B2B2B", "stroke-width": 4 }, F);
    el("path", { d: "M11,-6 L15,-6", stroke: "#2B2B2B", "stroke-width": 4 }, F);
  }
  drawHairFront(H, c);
  // lead arm (in front), with the phone it may hold
  P.leadArm = el("g", {}, body);
  P.leadUpper = limb(c.sleeve, 34, P.leadArm);
  P.leadFore = limb(c.forearm, 30, P.leadArm);
  P.phone = el("g", { visibility: "hidden" }, P.leadArm);
  el("rect", { x: -15, y: -50, width: 30, height: 56, rx: 7, fill: "#F7F7F9" }, P.phone);
  el("rect", { x: -11, y: -45, width: 22, height: 44, rx: 4, fill: "#15151A" }, P.phone);
  P.leadHand = el("circle", { r: 17, fill: c.skin }, P.leadArm);
  return { root, body, shadow, P, c };
}

function drawTop(g, c) {
  const sh = RIG.shY, hp = RIG.hipY;
  const torso = `M${-RIG.shX - 10},${sh + 8} Q${-RIG.shX - 6},${sh - 16} ${-30},${sh - 18} L30,${sh - 18} Q${RIG.shX + 6},${sh - 16} ${RIG.shX + 10},${sh + 8}
                 L${RIG.hipX + 30},${hp + 14} Q0,${hp + 26} ${-RIG.hipX - 30},${hp + 14} Z`;
  if (c.top === "dress") {   // kitenge: shoulders to mid-shin, flared
    const d = `M${-RIG.shX - 10},${sh + 8} Q${-RIG.shX - 6},${sh - 16} -30,${sh - 18} L30,${sh - 18} Q${RIG.shX + 6},${sh - 16} ${RIG.shX + 10},${sh + 8}
               L${RIG.shX + 46},-58 Q0,-40 ${-RIG.shX - 46},-58 Z`;
    el("path", { d, fill: c.topColor }, g);
    const pat = el("g", { "clip-path": `url(#clip-${c.key})` }, g);
    const cp = el("clipPath", { id: `clip-${c.key}` }, g);
    el("path", { d }, cp);
    for (let y = sh; y < -40; y += 46) for (let x = -110; x < 110; x += 46) {
      const o = ((y / 46) | 0) % 2 ? 23 : 0;
      el("circle", { cx: x + o, cy: y, r: 13, fill: c.pattern, opacity: .85 }, pat);
      el("circle", { cx: x + o, cy: y, r: 5, fill: c.topColor }, pat);
    }
    el("path", { d: `M-24,${sh - 16} Q0,${sh + 10} 24,${sh - 16}`, fill: "none", stroke: c.pattern, "stroke-width": 7 }, g);
    return;
  }
  el("path", { d: torso, fill: c.topColor }, g);
  if (c.top === "hoodie") {
    el("path", { d: `M-34,${sh - 18} Q0,${sh + 22} 34,${sh - 18}`, fill: "none", stroke: c.trim, "stroke-width": 10, "stroke-linecap": "round" }, g);
    el("path", { d: `M-10,${sh} L-12,${sh + 60} M12,${sh} L14,${sh + 56}`, stroke: c.trim, "stroke-width": 5, "stroke-linecap": "round" }, g);
    el("path", { d: `M-40,${hp - 70} L40,${hp - 70} L32,${hp - 18} L-32,${hp - 18} Z`, fill: "rgba(0,0,0,.10)" }, g);
  } else if (c.top === "jersey") {
    el("path", { d: `M-26,${sh - 18} L0,${sh + 16} L26,${sh - 18}`, fill: "none", stroke: c.trim, "stroke-width": 9, "stroke-linejoin": "round" }, g);
    el("text", { x: 4, y: sh + 112, "text-anchor": "middle", "font-family": "Unbounded", "font-weight": 800, "font-size": 70,
                 fill: c.trim }, g).textContent = c.number || "7";
  } else if (c.top === "jacket") {   // open jacket over a tee
    el("path", { d: `M-22,${sh - 18} L22,${sh - 18} L18,${hp + 18} L-18,${hp + 18} Z`, fill: c.tee }, g);
    el("path", { d: `M-22,${sh - 18} L-12,${hp + 16} M22,${sh - 18} L12,${hp + 16}`, stroke: "rgba(0,0,0,.18)", "stroke-width": 5 }, g);
  } else if (c.top === "bomber") {
    el("path", { d: `M-30,${sh - 18} Q0,${sh + 4} 30,${sh - 18}`, fill: "none", stroke: c.trim, "stroke-width": 12, "stroke-linecap": "round" }, g);
    el("path", { d: `M0,${sh - 8} L0,${hp + 18}`, stroke: "rgba(0,0,0,.22)", "stroke-width": 4 }, g);
    el("path", { d: `M${-RIG.hipX - 30},${hp + 4} Q0,${hp + 18} ${RIG.hipX + 30},${hp + 4}`, fill: "none", stroke: c.trim, "stroke-width": 14 }, g);
  } else if (c.top === "vest") {   // shirt under a knit vest
    el("path", { d: `M-28,${sh - 18} L0,${sh + 52} L28,${sh - 18}`, fill: c.tee }, g);
    el("path", { d: `M-8,${sh - 16} L0,${sh + 40} L8,${sh - 16}Z`, fill: c.tie || "#2D3B5A" }, g);
    for (let y = sh + 20; y < hp; y += 22) el("path", { d: `M-50,${y} L50,${y}`, stroke: "rgba(0,0,0,.08)", "stroke-width": 3 }, g);
  }
}

function drawHairBack(H, c) {
  if (c.hair === "braids") {
    for (let i = 0; i < 9; i++) {
      const x = -70 + i * 15;
      el("rect", { x: x - 8, y: -50, width: 16, height: 170 - Math.abs(i - 4) * 8, rx: 8, fill: c.hairColor }, H);
    }
  } else if (c.hair === "wrap") {
    el("path", { d: "M-70,-10 Q-84,-120 0,-132 Q84,-120 70,-10 Z", fill: c.hairColor }, H);
  }
}

function drawHairFront(H, c) {
  const hc = c.hairColor;
  if (c.hair === "fade") {
    el("path", { d: "M-64,-8 C-68,-62 -40,-88 2,-88 C44,-88 68,-62 64,-8 C54,-34 34,-46 2,-46 C-30,-46 -52,-34 -64,-8Z", fill: hc }, H);
    el("path", { d: "M-20,-80 L-6,-50", stroke: "rgba(255,255,255,.35)", "stroke-width": 3, "stroke-linecap": "round" }, H);
  } else if (c.hair === "braids") {
    el("path", { d: "M-66,-2 C-70,-66 -38,-90 2,-90 C46,-90 70,-62 66,-6 C56,-40 30,-50 4,-50 C-28,-50 -54,-36 -66,-2Z", fill: hc }, H);
    el("path", { d: "M2,-90 L4,-52", stroke: "rgba(255,255,255,.18)", "stroke-width": 3 }, H);
    for (let i = 0; i < 3; i++) el("rect", { x: -76 + i * 13, y: -20, width: 14, height: 150, rx: 7, fill: hc }, H);
  } else if (c.hair === "twists") {
    el("path", { d: "M-64,-6 C-68,-60 -40,-86 0,-86 C42,-86 68,-60 64,-6 C52,-34 30,-44 0,-44 C-30,-44 -52,-34 -64,-6Z", fill: hc }, H);
    for (let i = 0; i < 9; i++) {
      const a = Math.PI * (1.05 + i * 0.112);
      el("circle", { cx: Math.cos(a) * 66, cy: -14 + Math.sin(a) * 74, r: 15, fill: hc }, H);
    }
  } else if (c.hair === "cap") {   // backwards cap
    el("path", { d: "M-66,-10 C-70,-70 -36,-92 2,-92 C44,-92 70,-66 66,-10 Z", fill: c.capColor }, H);
    el("path", { d: "M-60,-20 Q-100,-26 -104,-6 Q-80,-4 -58,-4Z", fill: c.capColor }, H);
    el("path", { d: "M-66,-10 Q0,-30 66,-10", fill: "none", stroke: "rgba(0,0,0,.2)", "stroke-width": 4 }, H);
    el("circle", { cx: 2, cy: -90, r: 6, fill: c.capColor }, H);
  } else if (c.hair === "wrap") {
    el("path", { d: "M-70,-6 Q-76,-96 0,-104 Q76,-96 70,-6 Q40,-36 0,-38 Q-40,-36 -70,-6Z", fill: hc }, H);
    for (let i = 0; i < 5; i++) el("circle", { cx: -44 + i * 22, cy: -66 + (i % 2) * 14, r: 6, fill: c.pattern }, H);
    el("path", { d: "M10,-100 Q46,-150 60,-110 Q40,-118 26,-96Z", fill: hc }, H);
    el("path", { d: "M-6,-100 Q-40,-148 -58,-112 Q-36,-120 -20,-96Z", fill: hc }, H);
  } else if (c.hair === "grey") {
    el("path", { d: "M-64,4 C-70,-40 -54,-66 -28,-72 L-30,-56 C-46,-48 -54,-30 -56,4Z", fill: hc }, H);
    el("path", { d: "M64,0 C66,-40 52,-62 30,-70 L32,-56 C46,-46 54,-30 56,0Z", fill: hc }, H);
    el("path", { d: "M-40,-66 Q0,-84 40,-66", fill: "none", stroke: hc, "stroke-width": 8, "stroke-linecap": "round", opacity: .7 }, H);
  }
}

// ---------------------------------------------------------------------------------------------------------------
// Faces
// ---------------------------------------------------------------------------------------------------------------
const MOUTHS = {
  neutral: "M14,36 Q26,40 38,35",
  happy: "M10,32 Q26,48 42,31 Q26,40 10,32Z",
  laugh: "M8,30 Q26,62 44,29 Q26,34 8,30Z",
  sad: "M12,42 Q26,32 40,42",
  angry: "M12,40 Q26,34 40,40",
  shock: "M18,32 Q26,22 34,32 Q36,48 26,50 Q16,48 18,32Z",
  smug: "M12,38 Q30,42 42,30",
  talk1: "M12,32 Q26,30 40,32 Q36,48 26,48 Q16,48 12,32Z",
  talk2: "M14,33 Q26,32 38,33 Q34,42 26,42 Q18,42 14,33Z",
  talk3: "M10,31 Q26,29 42,31 Q38,54 26,54 Q14,54 10,31Z",
};
// brows: [left inner y, left outer y, right inner y, right outer y] offsets around y -34
const BROWS = { neutral: [0, 0, 0, 0], happy: [-4, -2, -4, -2], laugh: [-6, -2, -6, -2], sad: [-10, 4, -10, 4],
                angry: [8, -6, 8, -6], shock: [-14, -12, -14, -12], smug: [2, 2, -10, -6] };
const EYES = { neutral: 1, happy: 0.85, laugh: 0.2, sad: 0.9, angry: 0.62, shock: 1.3, smug: 0.6 };

function setFace(P, face, talk, blink) {
  const b = BROWS[face] || BROWS.neutral;
  P.browL.setAttribute("d", `M-20,${-34 + b[1]} Q-6,${-40 + (b[0] + b[1]) / 2} 4,${-32 + b[0]}`);
  P.browR.setAttribute("d", `M20,${-32 + b[2]} Q32,${-40 + (b[2] + b[3]) / 2} 46,${-34 + b[3]}`);
  P.mouth.setAttribute("d", MOUTHS[talk || face] || MOUTHS.neutral);
  const open = blink ? 0.08 : (EYES[face] || 1);
  for (const e of [P.eyeL, P.eyeR]) {
    const big = Math.max(1, open);
    e.white.setAttribute("rx", 12 * Math.min(big, 1.15));
    e.white.setAttribute("ry", 14 * big);
    const shut = Math.max(0, Math.min(1, 1 - open));
    e.lid.setAttribute("height", (30 * shut).toFixed(1));
    e.pupil.setAttribute("r", face === "shock" ? 5.5 : 7);
  }
}

// ---------------------------------------------------------------------------------------------------------------
// Poses: where the hands and feet go (body coordinates, facing right; "lead" is the arm toward the facing side)
// ---------------------------------------------------------------------------------------------------------------
const STAND = { lead: [78, -246], back: [-78, -246], footB: [-26, 0], footF: [30, 0], lean: 0, tilt: 0, bob: 0, drop: 0,
                shrug: 0, phone: 0, down: 0, x: 0 };
const SIT = { ...STAND, lead: [74, -238], back: [26, -244], footB: [62, 0], footF: [100, 0], drop: 104 };
const NUM = ["lead", "back", "footB", "footF", "lean", "tilt", "bob", "drop", "shrug", "phone", "down", "x"];

function mix(a, b, k) {
  const o = {};
  for (const f of NUM) {
    const x = a[f], y = b[f] === undefined ? a[f] : b[f];
    o[f] = Array.isArray(x) ? [lerp(x[0], y[0], k), lerp(x[1], y[1], k)] : lerp(x, y, k);
  }
  return o;
}

// Each action: its length (null: holds until the character's next action) and the pose at u seconds in
const ACTIONS = {
  point:    { len: 1.7, at: (u) => ({ lead: [212, -476], tilt: -3 }) },
  shrug:    { len: 1.5, at: (u) => ({ lead: [150, -330], back: [-150, -330], shrug: 16, tilt: 8, down: 1 }) },
  facepalm: { len: 1.9, at: (u) => ({ lead: [30, -532], tilt: 14, lean: 4 }) },
  phone:    { len: null, at: (u) => ({ lead: [70, -548], phone: 1, tilt: -6 }) },
  knock:    { len: 1.5, at: (u) => ({ lead: [196 + 22 * Math.max(0, Math.sin(u * 22)), -488], lean: 3 }) },
  wave:     { len: 1.5, at: (u) => ({ lead: [132 + 26 * Math.sin(u * 13), -640], tilt: -4 }) },
  cross:    { len: null, at: (u) => ({ lead: [-34, -356], back: [44, -350], tilt: 4, down: 1 }) },
  think:    { len: 2.0, at: (u) => ({ lead: [34, -484], back: [-10, -330], tilt: 9 }) },
  laugh:    { len: 1.8, at: (u) => ({ lead: [40, -318], back: [-34, -318], lean: -5, tilt: -12, bob: 9 * Math.abs(Math.sin(u * 13)), down: 1 }) },
  angry:    { len: null, at: (u) => ({ lead: [100, -262], back: [-100, -262], lean: 4 }) },
  cheer:    { len: 1.6, at: (u) => ({ lead: [128, -668], back: [-128, -668], bob: 26 * Math.abs(Math.sin(u * 6.5)) }) },
  beg:      { len: 1.8, at: (u) => ({ lead: [70, -400], back: [40, -404], tilt: 10, lean: 6, down: 1 }) },
  none:     { len: 0, at: (u) => ({}) },
};
const STEP = 2 * Math.PI / 0.62;   // one stride every 0.62 s (the walk's length comes from the timeline)

// The pose of one character at time t, and where it stands (x) and whether it is on screen
function poseAt(ch, t, scene) {
  const base = ch.seated ? SIT : STAND;
  let pose = { ...base, lead: [...base.lead], back: [...base.back], footB: [...base.footB], footF: [...base.footF] };
  // idle: breathing and a slow sway
  pose.bob += 2.2 * Math.sin(t * 2.1 + ch.seed);
  pose.tilt += 1.6 * Math.sin(t * 0.9 + ch.seed * 2);
  // the actions this character takes, in order; a sticky one holds until the next
  const acts = ch.acts;
  for (let i = 0; i < acts.length; i++) {
    const a = acts[i], A = ACTIONS[a.do];
    if (!A || t < a.at) continue;
    const next = acts.slice(i + 1).find((x) => ACTIONS[x.do] && x.do !== "none");
    const until = A.len === null ? (next ? next.at : 1e9) : a.at + A.len;
    if (t >= until + 0.3) continue;
    const k = Math.min(smooth((t - a.at) / 0.22), smooth((until + 0.3 - t) / 0.3));
    pose = mix(pose, A.at(t - a.at), k);
  }
  // talking: a small nod
  const line = scene.lines.find((l) => l.who === ch.key && t >= l.start && t < l.talk_end);
  if (line) pose.tilt += 2.4 * Math.sin((t - line.start) * 8.5);
  // walking in or out: the body travels and the feet stride
  const WALK_S = scene.walk_s || 1.0;
  let x = ch.x, visible = true, walking = false, dir = 0;
  if (ch.enter !== null && ch.enter !== undefined) {
    if (t < ch.enter) visible = false;
    else if (t < ch.enter + WALK_S) {   // eased only at the end: they arrive, they don't fade in
      walking = true; dir = ch.from;
      const k = (t - ch.enter) / WALK_S;
      x = ch.x + ch.from * ch.walk * (1 - (k < 0.6 ? k / 0.75 : 0.8 + 0.2 * smooth((k - 0.6) / 0.4)));
    }
  }
  if (ch.exit !== null && ch.exit !== undefined && t >= ch.exit) {
    if (t >= ch.exit + WALK_S) visible = false;
    else { walking = true; dir = ch.to; x = ch.x + ch.to * (ch.walk + 60) * smooth((t - ch.exit) / WALK_S) ** 1.3; }
  }
  if (walking) {
    const ph = t * STEP;
    pose.footF = [36 + 46 * Math.sin(ph), -Math.max(0, 26 * Math.cos(ph))];
    pose.footB = [-30 - 46 * Math.sin(ph), -Math.max(0, -26 * Math.cos(ph))];
    pose.lead = [78 - 40 * Math.sin(ph), -250];
    pose.back = [-78 + 40 * Math.sin(ph), -250];
    pose.bob += 7 * Math.abs(Math.sin(ph));
    pose.drop = 0;
  }
  return { pose, x, visible, walking, dir };
}

function pickBend(S, T, a, b, prefer) {
  const s1 = ik(S, T, a, b, 1), s2 = ik(S, T, a, b, -1);
  return prefer(s1.E) >= prefer(s2.E) ? s1 : s2;
}

function shoePath(f) {
  const [x, y] = f;
  return `M${x - 26},${y + 2} Q${x - 30},${y - 34} ${x - 2},${y - 34} L${x + 30},${y - 20} Q${x + 48},${y - 10} ${x + 42},${y + 4} Z`;
}

// Puts one character's pose on its drawing
function applyPose(ch, st, facing, scale, floor, face, talk, blink) {
  const { pose } = st;
  const { root, body, shadow, P, c } = ch.g;
  root.setAttribute("visibility", st.visible ? "visible" : "hidden");
  root.setAttribute("transform", `translate(${st.x.toFixed(1)} ${floor}) scale(${(scale * facing).toFixed(3)} ${scale})`);
  const dy = pose.drop - pose.bob;
  body.setAttribute("transform", `translate(0 ${dy.toFixed(1)}) rotate(${pose.lean.toFixed(2)} 0 ${RIG.hipY})`);
  shadow.setAttribute("rx", (92 - Math.min(30, Math.max(0, pose.bob))).toFixed(1));
  P.head.setAttribute("transform", `rotate(${pose.tilt.toFixed(2)} 0 ${RIG.neckY})`);
  const up = -pose.shrug;
  const SL = [RIG.shX - 4, RIG.shY + up], SB = [-RIG.shX + 4, RIG.shY + up];
  // elbows go out to the side, or down by the body when the pose says so (a shrug, folded arms)
  const L = pickBend(SL, pose.lead, RIG.upper, RIG.fore, (E) => (1 - pose.down) * (E[0] + 0.4 * E[1]) + pose.down * 2 * E[1]);
  const B = pickBend(SB, pose.back, RIG.upper, RIG.fore, (E) => (1 - pose.down) * (-E[0] + 0.4 * E[1]) + pose.down * 2 * E[1]);
  const seg = (A, E) => `M${A[0].toFixed(1)},${A[1].toFixed(1)} L${E[0].toFixed(1)},${E[1].toFixed(1)}`;
  P.leadUpper.setAttribute("d", seg(SL, L.E)); P.leadFore.setAttribute("d", seg(L.E, L.T));
  P.backUpper.setAttribute("d", seg(SB, B.E)); P.backFore.setAttribute("d", seg(B.E, B.T));
  P.leadHand.setAttribute("cx", L.T[0].toFixed(1)); P.leadHand.setAttribute("cy", L.T[1].toFixed(1));
  P.backHand.setAttribute("cx", B.T[0].toFixed(1)); P.backHand.setAttribute("cy", B.T[1].toFixed(1));
  P.phone.setAttribute("visibility", pose.phone > 0.5 ? "visible" : "hidden");
  P.phone.setAttribute("transform", `translate(${(L.T[0] + 6).toFixed(1)} ${(L.T[1] + 4).toFixed(1)}) rotate(-12)`);
  if (P.book) P.book.setAttribute("transform", `translate(${B.T[0].toFixed(1)} ${(B.T[1] - 4).toFixed(1)}) rotate(-8)`);
  // legs: feet are given on the floor (root coordinates); the body may be lowered (sitting) or bouncing
  // the leg ends at the ankle, inside the shoe (a round end below the shoe would show)
  const fB = [pose.footB[0], pose.footB[1] - dy - RIG.ankle], fF = [pose.footF[0], pose.footF[1] - dy - RIG.ankle];
  const HB = [-RIG.hipX, RIG.hipY], HF = [RIG.hipX, RIG.hipY];
  const kB = pickBend(HB, fB, RIG.thigh, RIG.shin, (E) => E[0]);
  const kF = pickBend(HF, fF, RIG.thigh, RIG.shin, (E) => E[0]);
  P.legB.setAttribute("d", `M${HB[0]},${HB[1]} L${kB.E[0].toFixed(1)},${kB.E[1].toFixed(1)} L${kB.T[0].toFixed(1)},${kB.T[1].toFixed(1)}`);
  P.legF.setAttribute("d", `M${HF[0]},${HF[1]} L${kF.E[0].toFixed(1)},${kF.E[1].toFixed(1)} L${kF.T[0].toFixed(1)},${kF.T[1].toFixed(1)}`);
  P.shoeB.setAttribute("d", shoePath([kB.T[0], kB.T[1] + RIG.ankle])); P.shoeF.setAttribute("d", shoePath([kF.T[0], kF.T[1] + RIG.ankle]));
  setFace(P, face, talk, blink);
}

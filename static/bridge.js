/* Site editor bridge: runs inside the design preview page (same origin as the editor).
   Draws selection, resize handles, drag-to-reorder, and in-place text editing, and reports
   every change to the editor window (window.parent.SE). The editor turns those into CSS
   rules, HTML source edits or data-file edits. Editing chrome lives in a shadow root so the
   site's CSS cannot affect it and it never ends up in saved HTML. */
(function () {
  "use strict";
  var SE = window.parent && window.parent.SE;
  if (!SE) return;

  var SNAPS = [25, 33.333, 50, 66.667, 75, 100];
  var TEXT_TAGS = /^(H[1-6]|P|SPAN|A|LI|DT|DD|B|STRONG|I|EM|SMALL|LABEL|BUTTON|FIGCAPTION|BLOCKQUOTE|TD|TH|DIV)$/;
  var host = document.createElement("div");
  host.setAttribute("data-se-chrome", "");
  host.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none;";
  document.documentElement.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML = [
    "<style>",
    ":host{all:initial}",
    "[hidden]{display:none!important}",
    "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI','Noto Sans KR',sans-serif}",
    ".box{position:absolute;pointer-events:none;border:1.5px solid #2f6fed;border-radius:2px}",
    ".hover{position:absolute;pointer-events:none;border:1px dashed #2f6fed;background:rgba(47,111,237,.06)}",
    ".tag{position:absolute;top:-22px;left:-1px;background:#2f6fed;color:#fff;font-size:11px;padding:3px 6px;border-radius:4px 4px 0 0;white-space:nowrap}",
    ".h{position:absolute;width:11px;height:11px;background:#fff;border:2px solid #2f6fed;border-radius:3px;pointer-events:auto}",
    ".h.nw{left:-6px;top:-6px;cursor:nwse-resize}.h.ne{right:-6px;top:-6px;cursor:nesw-resize}",
    ".h.sw{left:-6px;bottom:-6px;cursor:nesw-resize}.h.se{right:-6px;bottom:-6px;cursor:nwse-resize}",
    ".h.n{left:50%;top:-6px;margin-left:-6px;cursor:ns-resize}.h.s{left:50%;bottom:-6px;margin-left:-6px;cursor:ns-resize}",
    ".h.w{top:50%;left:-6px;margin-top:-6px;cursor:ew-resize}.h.e{top:50%;right:-6px;margin-top:-6px;cursor:ew-resize}",
    ".bar{position:absolute;width:max-content;white-space:nowrap;align-items:center;display:flex;gap:2px;background:#1d2433;padding:3px;border-radius:8px;pointer-events:auto;box-shadow:0 4px 14px rgba(0,0,0,.25)}",
    ".bar button,.bar select,.bar input{all:unset;cursor:pointer;color:#fff;font-size:12px;padding:4px 7px;border-radius:5px;line-height:16px;min-width:14px;text-align:center}",
    ".bar button:hover{background:#38425a}.bar button.on{background:#2f6fed}",
    ".bar select{background:#2a3246;padding:3px 6px}.bar select option{color:#000}",
    ".bar input[type=color]{width:22px;height:20px;padding:0;border-radius:4px;overflow:hidden}",
    ".bar .sep{width:1px;background:#3b4560;margin:2px 3px}",
    ".bar .val{color:#9fb6ff;padding:4px 4px;font-size:12px;min-width:44px;text-align:center}",
    ".grip{cursor:grab!important}",
    ".guide{position:absolute;background:#ff3d7f;pointer-events:none}",
    ".ins{position:absolute;background:#ff3d7f;pointer-events:none;border-radius:2px;box-shadow:0 0 0 2px rgba(255,61,127,.25)}",
    ".tip{position:absolute;background:#ff3d7f;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;pointer-events:none;white-space:nowrap}",
    ".ghost{position:absolute;pointer-events:none;border:2px dashed #ff3d7f;background:rgba(255,61,127,.08);border-radius:4px}",
    "</style>",
    '<div class="hover" hidden></div>',
    '<div class="box" hidden><div class="tag"></div>',
    '<div class="h nw" data-h="nw"></div><div class="h n" data-h="n"></div><div class="h ne" data-h="ne"></div>',
    '<div class="h w" data-h="w"></div><div class="h e" data-h="e"></div>',
    '<div class="h sw" data-h="sw"></div><div class="h s" data-h="s"></div><div class="h se" data-h="se"></div></div>',
    '<div class="bar actions" hidden>',
    '<button class="grip" data-a="drag" title="끌어서 순서 바꾸기">⠿ 이동</button>',
    '<button data-a="up" title="앞으로">↑</button><button data-a="down" title="뒤로">↓</button>',
    '<span class="sep"></span><button data-a="parent" title="감싸는 요소 고르기">⬑ 부모</button>',
    '<button data-a="text" title="글자 편집 (두 번 클릭)">✎ 글자</button></div>',
    '<div class="bar textbar" hidden>',
    '<select data-t="font" title="폰트"></select>',
    '<button data-t="smaller" title="작게">A−</button><span class="val" data-t="size"></span><button data-t="bigger" title="크게">A+</button>',
    '<span class="sep"></span><button data-t="bold" title="굵게"><b>B</b></button><button data-t="italic" title="기울임"><i>I</i></button>',
    '<input type="color" data-t="color" title="글자 색">',
    '<span class="sep"></span><button data-t="left" title="왼쪽">⇤</button><button data-t="center" title="가운데">≡</button><button data-t="right" title="오른쪽">⇥</button>',
    '<span class="sep"></span><button data-t="done" title="완료 (Ctrl+Enter)">완료</button><button data-t="cancel" title="취소 (Esc)">✕</button></div>',
    '<div class="tip" hidden></div><div class="ghost" hidden></div><div class="ins" hidden></div>'
  ].join("");
  var I18N = window.parent.SE_I18N;
  var T = I18N ? I18N.T : function (x) { return x; };
  if (I18N) I18N.observe(root);  // toolbar labels and tooltips in the chosen language
  var $ = function (s) { return root.querySelector(s); };
  var hoverBox = $(".hover"), box = $(".box"), tagEl = $(".tag"), actions = $(".actions"), textbar = $(".textbar");
  var tip = $(".tip"), ghost = $(".ghost"), ins = $(".ins");
  var guides = [];
  var sel = null, editing = null, editOrig = "", drag = null, resize = null;

  // ---------- helpers ----------
  function chrome(n) { return n === host || (n && n.closest && n.closest("[data-se-chrome]")); }
  function rootPx() { return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16; }
  function rem(px) { return Math.round(px / rootPx() * 1000) / 1000; }
  function pageRect(el) {
    var r = el.getBoundingClientRect();
    return { left: r.left + scrollX, top: r.top + scrollY, width: r.width, height: r.height, right: r.right + scrollX, bottom: r.bottom + scrollY };
  }
  function place(n, r) { n.style.left = r.left + "px"; n.style.top = r.top + "px"; n.style.width = r.width + "px"; n.style.height = r.height + "px"; }
  function cssName(s) { return /^[A-Za-z_][A-Za-z0-9_-]*$/.test(s) ? s : null; }
  function idOf(el) { return el.id && cssName(el.id) ? "#" + el.id : null; }
  function selectorOne(el) {
    if (idOf(el)) return idOf(el);
    var parts = [], n = el;
    while (n && n !== document.body && n.nodeType === 1) {
      if (idOf(n)) { parts.unshift(idOf(n)); return parts.join(" > "); }
      var k = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) k++;
      parts.unshift(n.tagName.toLowerCase() + ":nth-of-type(" + k + ")");
      n = n.parentElement;
    }
    parts.unshift("body");
    return parts.join(" > ");
  }
  function selectorKind(el) {
    var cls = Array.prototype.filter.call(el.classList, function (c) { return cssName(c); });
    var own = el.tagName.toLowerCase() + cls.map(function (c) { return "." + c; }).join("");
    var a = el.parentElement;
    while (a && a !== document.body && !idOf(a)) a = a.parentElement;
    return (a && a !== document.body ? idOf(a) + " " : "") + own;
  }
  function describe(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.classList.length) s += "." + Array.prototype.slice.call(el.classList, 0, 2).join(".");
    return s;
  }
  function movable(el) {
    if (el.hasAttribute("data-se-list")) return { kind: "list", list: el.getAttribute("data-se-list") };
    if (el.hasAttribute("data-se-id")) return { kind: "html" };
    return null;
  }
  function siblingsFor(el) {
    var m = movable(el);
    if (!m || !el.parentElement) return [];
    return Array.prototype.filter.call(el.parentElement.children, function (c) {
      if (chrome(c) || c.hidden) return false;
      return m.kind === "list" ? c.getAttribute("data-se-list") === m.list : c.hasAttribute("data-se-id");
    });
  }
  function horizontal(parent) {
    var cs = getComputedStyle(parent);
    return (cs.display.indexOf("flex") >= 0 && cs.flexDirection.indexOf("row") === 0) || cs.display.indexOf("grid") >= 0 && cs.gridTemplateColumns.split(" ").length > 1;
  }
  function info(el) {
    var cs = getComputedStyle(el), parent = el.parentElement, pw = parent ? parent.clientWidth : innerWidth;
    var pcs = parent ? getComputedStyle(parent) : null;
    var inner = pw - (pcs ? parseFloat(pcs.paddingLeft) + parseFloat(pcs.paddingRight) : 0);
    var kindSel = selectorKind(el);
    var count = 1;
    try { count = document.querySelectorAll(kindSel).length; } catch (e) {}
    return {
      tag: el.tagName.toLowerCase(), label: describe(el), selectorOne: selectorOne(el), selectorKind: kindSel, kindCount: count,
      path: el.getAttribute("data-se-path"), seId: el.hasAttribute("data-se-id") ? +el.getAttribute("data-se-id") : null,
      i18n: el.hasAttribute("data-i18n"), movable: !!movable(el), textEditable: textEditable(el),
      computed: {
        "font-family": cs.fontFamily, "font-size": rem(parseFloat(cs.fontSize)) + "rem", "font-weight": cs.fontWeight,
        "font-style": cs.fontStyle, color: cs.color, "background-color": cs.backgroundColor, "text-align": cs.textAlign,
        "line-height": cs.lineHeight, "letter-spacing": cs.letterSpacing,
        "margin-top": cs.marginTop, "margin-right": cs.marginRight, "margin-bottom": cs.marginBottom, "margin-left": cs.marginLeft,
        "padding-top": cs.paddingTop, "padding-right": cs.paddingRight, "padding-bottom": cs.paddingBottom, "padding-left": cs.paddingLeft,
        "border-radius": cs.borderTopLeftRadius,
        width: inner > 0 ? Math.round(el.getBoundingClientRect().width / inner * 1000) / 10 + "%" : "", display: cs.display
      }
    };
  }
  function textEditable(el) {
    if (!el || !TEXT_TAGS.test(el.tagName)) return false;
    if (el.querySelector("[data-se-path]") && !el.hasAttribute("data-se-path")) return false; // edit the inner data-bound piece
    if (!el.hasAttribute("data-se-path") && !el.hasAttribute("data-se-id")) return false;    // made by a script: not traceable
    return /\S/.test(el.textContent);
  }

  // ---------- drawing ----------
  function draw() {
    if (sel && !document.contains(sel)) sel = null;
    if (!sel) { box.hidden = actions.hidden = true; if (!editing) textbar.hidden = true; return; }
    var r = pageRect(sel);
    box.hidden = false; place(box, r);
    var nice = window.parent.friendly ? T(window.parent.friendly(sel.tagName.toLowerCase())) : describe(sel);
    tagEl.textContent = nice + "  " + Math.round(r.width) + "×" + Math.round(r.height);
    root.querySelectorAll(".h").forEach(function (h) { h.style.display = editing ? "none" : ""; });
    var bar = editing ? textbar : actions;
    (editing ? actions : textbar).hidden = true;
    bar.hidden = false;
    var top = r.top - bar.offsetHeight - 28;
    if (top < scrollY + 4) top = r.bottom + 8;
    bar.style.left = Math.max(scrollX + 4, Math.min(r.left, scrollX + innerWidth - bar.offsetWidth - 8)) + "px";
    bar.style.top = top + "px";
    var m = movable(sel);
    actions.querySelector('[data-a="drag"]').style.display = m ? "" : "none";
    actions.querySelector('[data-a="up"]').style.display = m ? "" : "none";
    actions.querySelector('[data-a="down"]').style.display = m ? "" : "none";
    actions.querySelector('[data-a="text"]').style.display = textEditable(sel) ? "" : "none";
    if (editing) syncTextbar();
  }
  var raf = 0;
  function redraw() { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); }
  addEventListener("scroll", redraw, true);
  addEventListener("resize", redraw);
  new MutationObserver(function () { if (!drag && !resize) redraw(); }).observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });

  function select(el) {
    if (editing && el !== editing) finishEdit(true);
    sel = el;
    hoverBox.hidden = true;
    draw();
    SE.select(el ? info(el) : null);
  }
  function clearGuides() { guides.forEach(function (g) { g.remove(); }); guides = []; tip.hidden = true; }
  function guide(x, y, w, h) { var g = document.createElement("div"); g.className = "guide"; place(g, { left: x, top: y, width: w, height: h }); root.appendChild(g); guides.push(g); }

  // ---------- picking ----------
  document.addEventListener("mousemove", function (e) {
    if (drag || resize) return;
    var t = e.target;
    if (chrome(t) || editing || t === document.documentElement || t === document.body) { hoverBox.hidden = true; return; }
    hoverBox.hidden = false; place(hoverBox, pageRect(t));
  }, true);
  var suppressClick = false;
  document.addEventListener("click", function (e) {
    if (chrome(e.target)) return;
    if (suppressClick) { suppressClick = false; e.preventDefault(); e.stopPropagation(); return; }
    if (editing && editing.contains(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    if (e.target === document.documentElement || e.target === document.body) return select(null);
    select(e.target);
  }, true);
  document.addEventListener("dblclick", function (e) {
    if (chrome(e.target) || editing) return;
    e.preventDefault();
    var t = e.target.closest("[data-se-path]") || e.target;
    if (!textEditable(t)) t = e.target;
    select(t);
    startEdit(t);
  }, true);
  ["submit", "auxclick"].forEach(function (ev) { document.addEventListener(ev, function (e) { if (!chrome(e.target)) e.preventDefault(); }, true); });

  // ---------- resize ----------
  root.querySelectorAll(".h").forEach(function (h) {
    h.addEventListener("mousedown", function (e) {
      if (!sel) return;
      e.preventDefault(); e.stopPropagation();
      var parent = sel.parentElement, pcs = getComputedStyle(parent);
      var inner = parent.clientWidth - parseFloat(pcs.paddingLeft) - parseFloat(pcs.paddingRight);
      var r = sel.getBoundingClientRect();
      resize = { dir: h.getAttribute("data-h"), x: e.clientX, y: e.clientY, w: r.width, h: r.height, inner: inner,
                 natural: sel.scrollHeight, img: sel.tagName === "IMG", props: {} };
    });
  });
  function onResizeMove(e) {
    if (!resize.moved && Math.hypot(e.clientX - resize.x, e.clientY - resize.y) < 4) return; // a click is not a resize
    resize.moved = true;
    var d = resize.dir, props = {}, label = [];
    var pr = pageRect(sel.parentElement), pcs = getComputedStyle(sel.parentElement);
    clearGuides();
    if (/[ew]/.test(d)) {
      var dx = (e.clientX - resize.x) * (d.indexOf("w") >= 0 ? -1 : 1);
      var pct = Math.max(5, Math.min(100, (resize.w + dx) / resize.inner * 100));
      if (!e.altKey) {
        var near = SNAPS.filter(function (s) { return Math.abs(s - pct) < 1.6; })[0];
        if (near) {
          pct = near;
          var x = pr.left + parseFloat(pcs.paddingLeft) + resize.inner * near / 100;
          guide(x, pr.top, 1.5, pr.height);
        } else pct = Math.round(pct);
      }
      props.width = (Math.round(pct * 10) / 10) + "%";
      props["max-width"] = "100%";
      if (resize.img) props.height = "auto";
      label.push(T("너비") + " " + props.width);
    }
    if (/[ns]/.test(d) && !resize.img) {
      var dy = (e.clientY - resize.y) * (d.indexOf("n") >= 0 ? -1 : 1);
      var hpx = Math.max(0, resize.h + dy);
      if (Math.abs(hpx - resize.natural) < 8 && !e.altKey) { props["min-height"] = ""; label.push(T("높이 자동")); }
      else { var r = Math.round(rem(hpx) * 4) / 4; props["min-height"] = r + "rem"; label.push(T("최소 높이") + " " + r + "rem"); }
    }
    resize.props = props;
    SE.setStyle(props, { commit: false });
    var br = pageRect(sel);
    tip.hidden = false; tip.textContent = label.join(" · ") + (e.altKey ? "" : "  " + T("(Alt: 스냅 끄기)"));
    tip.style.left = br.right + 8 + "px"; tip.style.top = br.bottom - 20 + "px";
  }

  // ---------- drag to reorder ----------
  actions.querySelector('[data-a="drag"]').addEventListener("mousedown", function (e) { if (sel) { e.preventDefault(); startDrag(e); } });
  document.addEventListener("mousedown", function (e) {
    if (chrome(e.target) || editing || !sel || e.button !== 0) return;
    if (sel.contains(e.target) && movable(sel)) drag = { pending: true, x: e.clientX, y: e.clientY };
  }, true);
  function startDrag(e) {
    var sibs = siblingsFor(sel);
    if (sibs.length < 2) { SE.toast("옮길 수 있는 같은 줄의 블록이 없습니다"); drag = null; return; }
    drag = { active: true, sibs: sibs, horiz: horizontal(sel.parentElement), target: null, where: null };
    ghost.hidden = false; place(ghost, pageRect(sel));
    document.documentElement.style.cursor = "grabbing";
  }
  function onDragMove(e) {
    var s0 = getSelection(); if (s0.rangeCount) s0.removeAllRanges();
    var r0 = pageRect(sel);
    ghost.style.left = r0.left + (e.clientX - (drag.sx || (drag.sx = e.clientX))) + "px";
    ghost.style.top = r0.top + (e.clientY - (drag.sy || (drag.sy = e.clientY))) + "px";
    var px = e.clientX + scrollX, py = e.clientY + scrollY, best = null, bestD = Infinity;
    drag.sibs.forEach(function (s) {
      var r = pageRect(s);
      var c = drag.horiz ? r.left + r.width / 2 : r.top + r.height / 2;
      var dist = drag.horiz ? Math.abs(px - c) + (py < r.top || py > r.bottom ? 1000 : 0) : Math.abs(py - c);
      if (dist < bestD) { bestD = dist; best = { el: s, where: (drag.horiz ? px < c : py < c) ? "before" : "after", r: r }; }
    });
    if (!best) return;
    drag.target = best.el; drag.where = best.where;
    ins.hidden = false;
    var r = best.r;
    if (drag.horiz) place(ins, { left: (best.where === "before" ? r.left : r.right) - 2, top: r.top, width: 4, height: r.height });
    else place(ins, { left: r.left, top: (best.where === "before" ? r.top : r.bottom) - 2, width: r.width, height: 4 });
  }
  function endDrag() {
    ghost.hidden = ins.hidden = true;
    document.documentElement.style.cursor = "";
    var d = drag; drag = null;
    suppressClick = true;
    setTimeout(function () { suppressClick = false; }, 300);
    if (!d || !d.target || d.target === sel) return;
    moveTo(sel, d.target, d.where);
  }
  function moveTo(el, target, where) {
    var m = movable(el);
    if (m.kind === "list") {
      var from = +el.getAttribute("data-se-index"), t = +target.getAttribute("data-se-index");
      var to = where === "before" ? t : t + 1;
      if (from < to) to -= 1;
      if (from === to) return;
      SE.moveListItem(m.list, from, to);
    } else {
      if (!target.hasAttribute("data-se-id")) return;
      target.parentElement.insertBefore(el, where === "before" ? target : target.nextSibling);
      SE.moveElement(+el.getAttribute("data-se-id"), +target.getAttribute("data-se-id"), where);
      redraw();
    }
  }
  actions.addEventListener("click", function (e) {
    var a = e.target.closest("[data-a]"); if (!a || !sel) return;
    var act = a.getAttribute("data-a");
    if (act === "parent" && sel.parentElement && sel.parentElement !== document.documentElement) select(sel.parentElement === document.body ? sel : sel.parentElement);
    if (act === "text") startEdit(sel);
    if (act === "up" || act === "down") {
      var sibs = siblingsFor(sel), i = sibs.indexOf(sel);
      var j = act === "up" ? i - 1 : i + 1;
      if (j < 0 || j >= sibs.length) return SE.toast(act === "up" ? "이미 맨 앞입니다" : "이미 맨 뒤입니다");
      moveTo(sel, sibs[j], act === "up" ? "before" : "after");
    }
  });

  document.addEventListener("mousemove", function (e) {
    if (resize) return onResizeMove(e);
    if (drag && drag.pending && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 6) { startDrag(e); }
    if (drag && drag.active) onDragMove(e);
  }, true);
  document.addEventListener("mouseup", function () {
    if (resize) {
      clearGuides();
      if (resize.moved) SE.setStyle(resize.props, { commit: true });
      resize = null; SE.select(info(sel));
      suppressClick = true; setTimeout(function () { suppressClick = false; }, 300);
      return;
    }
    if (drag && drag.active) return endDrag();
    drag = null;
  }, true);

  // ---------- in-place text editing ----------
  var FONTS = [["", "폰트 (그대로)"], ["Pretendard, 'Noto Sans KR', sans-serif", "Pretendard"], ["'Noto Sans KR', sans-serif", "Noto Sans KR"],
    ["'Nanum Gothic', sans-serif", "나눔고딕"], ["'Nanum Myeongjo', serif", "나눔명조"], ["'Gowun Dodum', sans-serif", "고운돋움"],
    ["'IBM Plex Sans KR', sans-serif", "IBM Plex Sans KR"], ["Inter, sans-serif", "Inter"], ["'Playfair Display', serif", "Playfair Display"],
    ["Georgia, serif", "Georgia (serif)"], ["ui-monospace, Consolas, monospace", "고정폭"]];
  var fontSel = textbar.querySelector('[data-t="font"]');
  FONTS.forEach(function (f) { var o = document.createElement("option"); o.value = f[0]; o.textContent = f[1]; fontSel.appendChild(o); });

  function startEdit(el) {
    if (!textEditable(el)) return SE.toast(el && el.hasAttribute("data-i18n") ? "이 글자는 언어 설정 스크립트가 채웁니다 (파일 탭에서 수정)" : "이 요소는 바로 편집할 수 없습니다. 안쪽 글자를 두 번 클릭해 보세요");
    if (el.hasAttribute("data-i18n")) return SE.toast("이 글자는 언어 설정 스크립트가 채웁니다 (파일 탭에서 수정)");
    editing = el; editOrig = el.innerHTML;
    el.setAttribute("contenteditable", "true");
    el.setAttribute("spellcheck", "false");
    el.focus();
    var r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
    var s = getSelection(); s.removeAllRanges(); s.addRange(r);
    draw();
    SE.editing(true);
  }
  function cleanHTML(el) {
    var c = el.cloneNode(true);
    c.querySelectorAll("[contenteditable],[spellcheck]").forEach(function (n) { n.removeAttribute("contenteditable"); n.removeAttribute("spellcheck"); });
    c.querySelectorAll("span:not([style]):not([class]):not([id])").forEach(function (n) { n.replaceWith.apply(n, Array.prototype.slice.call(n.childNodes)); });
    c.querySelectorAll("br:last-child").forEach(function (n) { if (!n.nextSibling) n.remove(); });
    return c.innerHTML.replace(/&nbsp;/g, " ").replace(/ /g, " ");
  }
  function finishEdit(keep) {
    var el = editing; if (!el) return;
    editing = null;
    el.removeAttribute("contenteditable"); el.removeAttribute("spellcheck");
    if (!keep) el.innerHTML = editOrig;
    else if (el.innerHTML !== editOrig) {
      var html = cleanHTML(el);
      if (el.hasAttribute("data-se-path")) {
        var plain = !/<[a-z]/i.test(html);
        SE.setText({ path: el.getAttribute("data-se-path") }, plain ? el.textContent : html);
      } else SE.setText({ seId: +el.getAttribute("data-se-id") }, html);
    }
    SE.editing(false);
    draw();
  }
  function selectionInside() {
    var s = getSelection();
    if (!editing || !s.rangeCount || s.isCollapsed) return null;
    var r = s.getRangeAt(0);
    return editing.contains(r.commonAncestorContainer) ? r : null;
  }
  function wrap(range, styleProps, tag) {
    var anc = range.commonAncestorContainer;
    if (anc.nodeType === 3) anc = anc.parentElement;
    if (!tag && anc !== editing && anc.tagName === "SPAN" && anc.textContent === range.toString()) {
      Object.keys(styleProps).forEach(function (k) { anc.style.setProperty(k, styleProps[k]); }); // restyle, do not nest
      return;
    }
    var span = document.createElement(tag || "span");
    if (styleProps) Object.keys(styleProps).forEach(function (k) { span.style.setProperty(k, styleProps[k]); });
    span.appendChild(range.extractContents());
    range.insertNode(span);
    var s = getSelection(); s.removeAllRanges(); var r = document.createRange(); r.selectNodeContents(span); s.addRange(r);
  }
  function curSizeRem(node) { return rem(parseFloat(getComputedStyle(node).fontSize)); }
  function syncTextbar() {
    if (!editing) return;
    var r = selectionInside(), node = r ? (r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement) : editing;
    textbar.querySelector('[data-t="size"]').textContent = T("{n}배", { n: curSizeRem(node) });
    var cs = getComputedStyle(editing);
    ["left", "center", "right"].forEach(function (a) { textbar.querySelector('[data-t="' + a + '"]').classList.toggle("on", cs.textAlign === a || (a === "left" && cs.textAlign === "start")); });
  }
  document.addEventListener("selectionchange", function () { if (editing) syncTextbar(); });
  function applyText(props, wrapTag) {
    var r = selectionInside();
    if (r) { wrap(r, props, wrapTag); editing.dispatchEvent(new Event("input")); SE.toast("선택한 글자에만 적용"); }
    else SE.setStyle(props, { commit: true, element: editing });
    syncTextbar();
  }
  textbar.addEventListener("mousedown", function (e) { if (e.target.tagName !== "SELECT" && e.target.type !== "color") e.preventDefault(); }); // keep text selection
  textbar.addEventListener("click", function (e) {
    var b = e.target.closest("[data-t]"); if (!b || !editing) return;
    var t = b.getAttribute("data-t");
    var r = selectionInside(), node = r ? (r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement) : editing;
    if (t === "bigger" || t === "smaller") {
      var size = Math.max(0.5, Math.round((curSizeRem(node) + (t === "bigger" ? 0.125 : -0.125)) * 1000) / 1000);
      applyText({ "font-size": size + "rem" });
    }
    if (t === "bold") applyText(r ? null : { "font-weight": getComputedStyle(editing).fontWeight >= 600 ? "400" : "700" }, r ? "b" : null);
    if (t === "italic") applyText(r ? null : { "font-style": getComputedStyle(editing).fontStyle === "italic" ? "normal" : "italic" }, r ? "i" : null);
    if (t === "left" || t === "center" || t === "right") SE.setStyle({ "text-align": t }, { commit: true, element: editing });
    if (t === "done") finishEdit(true);
    if (t === "cancel") finishEdit(false);
  });
  fontSel.addEventListener("change", function () { if (editing && fontSel.value) applyText({ "font-family": fontSel.value }); fontSel.value = ""; });
  textbar.querySelector('[data-t="color"]').addEventListener("input", function (e) { if (editing) applyText({ color: e.target.value }); });
  document.addEventListener("keydown", function (e) {
    if (editing) {
      if (e.key === "Escape") { e.preventDefault(); finishEdit(false); }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); finishEdit(true); }
      if (e.key === "Enter" && !e.shiftKey && /^(H[1-6]|SPAN|A|B|STRONG|LABEL|BUTTON)$/.test(editing.tagName)) { e.preventDefault(); finishEdit(true); }
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? SE.redo() : SE.undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); SE.redo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); SE.save(); }
    if (e.key === "Escape") select(null);
    if (e.key === "Enter" && sel && textEditable(sel)) { e.preventDefault(); startEdit(sel); }
  }, true);
  document.addEventListener("focusout", function (e) {
    if (editing && e.target === editing) setTimeout(function () {
      if (editing && !editing.contains(document.activeElement) && document.activeElement !== host) finishEdit(true);
    }, 150);
  });

  // ---------- API for the editor window ----------
  window.SEB = {
    applyCss: function (css) { var s = document.getElementById("__se_live"); if (s) s.textContent = css; redraw(); },
    reselect: function (selector) {
      if (!selector) return;
      try { var el = document.querySelector(selector); if (el) select(el); } catch (e) {}
    },
    refreshInfo: function () { if (sel) SE.select(info(sel)); },
    count: function (selector) { try { return document.querySelectorAll(selector).length; } catch (e) { return 0; } },
    current: function () { return sel; },
    isEditing: function () { return !!editing; }
  };
  SE.ready();
})();

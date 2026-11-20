(() => {
  "use strict";

  const CFG = window.MAEULSUP_CONFIG || {};
  const SIDO_LONG = {
    서울: "서울특별시", 부산: "부산광역시", 대구: "대구광역시", 인천: "인천광역시", 광주: "광주광역시",
    대전: "대전광역시", 울산: "울산광역시", 세종: "세종특별자치시", 경기: "경기도", 강원: "강원특별자치도",
    충북: "충청북도", 충남: "충청남도", 전북: "전북특별자치도", 전남: "전라남도", 경북: "경상북도",
    경남: "경상남도", 제주: "제주특별자치도",
  };
  // 시·도청 위치(대략). 숲 기록이 없는 광역시(서울·울산 등)에서도 거리로 가까운 이야기를 찾으려고 쓴다.
  const SIDO_CENTER = {
    서울: [37.566, 126.978], 부산: [35.180, 129.075], 대구: [35.871, 128.601], 인천: [37.456, 126.705],
    광주: [35.160, 126.851], 대전: [36.350, 127.385], 울산: [35.539, 129.311], 세종: [36.480, 127.289],
    경기: [37.275, 127.009], 강원: [37.885, 127.730], 충북: [36.635, 127.491], 충남: [36.659, 126.673],
    전북: [35.820, 127.108], 전남: [34.816, 126.463], 경북: [36.576, 128.505], 경남: [35.238, 128.692],
    제주: [33.489, 126.498],
  };
  const SIDO_ALIAS = {};
  for (const [s, l] of Object.entries(SIDO_LONG)) {
    SIDO_ALIAS[s] = s; SIDO_ALIAS[l] = s;
  }
  Object.assign(SIDO_ALIAS, {
    강원도: "강원", 전라북도: "전북", 경기도: "경기", 충청북도: "충북", 충청남도: "충남", 전라남도: "전남",
    경상북도: "경북", 경상남도: "경남", 제주도: "제주", 전라도: "전남", 경상도: "경북",
  });

  const main = document.getElementById("main");
  const audio = document.getElementById("audio");
  const state = { forests: [], byId: {}, stories: {}, report: null, tone: "child", list: [], trip: [], idx: -1, speaking: false };

  try { state.tone = localStorage.getItem("tone") || "child"; } catch (e) { /* 저장소를 못 써도 기본값으로 */ }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const region = (f) => [SIDO_LONG[f.sido] || "", f.sigungu || ""].filter(Boolean).join(" ");
  const cleanName = (n) => n.replace(/\(.*?\)/g, "").trim();
  const storyText = (id, tone) => (state.stories[id]?.[tone] || []).map((s) => s.t).join(" ");
  // 이야기 길이(초): 음성 파일 길이, 없으면 글자 수로 어림 (측정값: 아이용 초당 약 6.3자, 어른용 약 7자)
  const seconds = (id, tone = state.tone) => {
    const st = state.stories[id];
    if (st?.sec?.[tone]) return st.sec[tone];
    const extra = tone === "child" ? (st?.find || "").length : 0;
    return Math.round((storyText(id, tone).length + extra) / (tone === "child" ? 6.3 : 7));
  };
  const duration = (sec) => (sec < 60 ? `${Math.max(10, Math.round(sec / 10) * 10)}초` : `${Math.round(sec / 60)}분`);
  const total = (ids) => duration(ids.reduce((a, id) => a + seconds(id), 0));
  const NEAR_KM = 60;   // 도착지에서 이 거리 안의 이야기를 이어 붙인다
  const MAX_LIST = 20;  // 한 번에 이어 듣는 최대 편수

  function dist(a, b) {
    const r = Math.PI / 180;
    const x = (b.lng - a.lng) * r * Math.cos(((a.lat + b.lat) / 2) * r);
    const y = (b.lat - a.lat) * r;
    return Math.sqrt(x * x + y * y) * 6371;
  }

  // ---------- 데이터 ----------
  async function load() {
    const get = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(p); return r.json(); });
    const [forests, stories, report] = await Promise.all([
      get("data/forests.json"), get("data/stories.json"), get("data/report.json").catch(() => null),
    ]);
    state.forests = forests;
    state.stories = stories;
    state.report = report;
    for (const f of forests) state.byId[f.id] = f;
  }

  const storyForests = () => state.forests.filter((f) => state.stories[f.id]);

  function centroid(list) {
    const pts = list.filter((f) => f.lat);
    if (!pts.length) return null;
    return { lat: pts.reduce((a, f) => a + f.lat, 0) / pts.length, lng: pts.reduce((a, f) => a + f.lng, 0) / pts.length };
  }

  function search(raw) {
    let q = raw.replace(/\s+/g, "").replace(/(가는길|가는중|여행|나들이|으로|로|에)$/, "");
    if (!q) return null;
    const withStory = storyForests();

    // 시군구
    const sgMatch = new Set();
    for (const f of state.forests) {
      if (!f.sigungu) continue;
      const base = f.sigungu.replace(/(시|군|구)$/, "");
      if (f.sigungu === q || base === q || (q.length >= 2 && f.sigungu.startsWith(q))) sgMatch.add(`${f.sido}|${f.sigungu}`);
    }
    if (sgMatch.size) {
      const inArea = (f) => sgMatch.has(`${f.sido}|${f.sigungu}`);
      const primary = withStory.filter(inArea);
      const sidos = new Set([...sgMatch].map((k) => k.split("|")[0]));
      const center = centroid(state.forests.filter(inArea));
      // 가까운 이야기: 도착지 중심에서 NEAR_KM 안, 가까운 순 (도 경계는 따지지 않음). 위치를 모르면 같은 도에서.
      let nearby = withStory.filter((f) => !inArea(f));
      if (center) {
        primary.sort((a, b) => (a.lat ? dist(center, a) : 1e9) - (b.lat ? dist(center, b) : 1e9));
        nearby = nearby.filter((f) => f.lat && dist(center, f) <= NEAR_KM).sort((a, b) => dist(center, a) - dist(center, b));
      } else {
        nearby = nearby.filter((f) => sidos.has(f.sido));
      }
      nearby = nearby.slice(0, Math.max(0, MAX_LIST - primary.length));
      const label = [...sgMatch].map((k) => k.split("|")[1]).filter((v, i, a) => a.indexOf(v) === i).join(", ");
      return { label, primary, nearby, center };
    }
    // 시도
    const sido = SIDO_ALIAS[q] || SIDO_ALIAS[q.replace(/(도|시)$/, "")];
    if (sido) {
      const primary = withStory.filter((f) => f.sido === sido);
      // 광역시는 시청 기준, 도는 숲들의 가운데 (없으면 도청)
      const fixed = SIDO_CENTER[sido] && { lat: SIDO_CENTER[sido][0], lng: SIDO_CENTER[sido][1] };
      const center = (/(시)$/.test(SIDO_LONG[sido]) && fixed) || centroid(state.forests.filter((f) => f.sido === sido)) || fixed;
      const nearby = primary.length || !center ? []
        : withStory.filter((f) => f.lat && dist(center, f) <= NEAR_KM).sort((a, b) => dist(center, a) - dist(center, b)).slice(0, MAX_LIST);
      return { label: SIDO_LONG[sido], primary, nearby, center };
    }
    // 숲 이름
    const byName = withStory.filter((f) => f.name.replace(/\s/g, "").includes(q));
    if (byName.length) return { label: raw.trim(), primary: byName, nearby: [], byName: true };
    const words = raw.trim().split(/\s+/);
    if (words.length > 1) {
      for (const w of words) {
        const r = search(w);
        if (r && !r.unknown) return r;
      }
    }
    // 아는 지명이 아님 (시군구·시도·숲 이름 어디에도 없음)
    return { label: raw.trim(), primary: [], nearby: [], unknown: true };
  }

  // 지금 있는 곳(휴대폰 위치) 근처 이야기. NEAR_KM 안에 없으면 가장 가까운 3편을 거리와 함께 보여준다.
  function nearSearch(center) {
    const all = storyForests().filter((f) => f.lat).sort((a, b) => dist(center, a) - dist(center, b));
    const within = all.filter((f) => dist(center, f) <= NEAR_KM).slice(0, MAX_LIST);
    return { label: "지금 있는 곳", primary: within, nearby: [], center, here: true,
      far: within.length ? [] : all.slice(0, 3) };
  }

  // 숲 화면에서 들을 때 이어 들을 목록: 방금 본 여행 목록에 있고 뒤에 이야기가 남았으면 그 목록의 그 자리부터,
  // 아니면 이 숲에서 NEAR_KM 안의 이야기를 가까운 순으로 붙인다.
  function queueFrom(id) {
    const at = state.trip.indexOf(id);
    if (at >= 0 && at < state.trip.length - 1) return { ids: state.trip, i: at };
    const f = state.byId[id];
    const near = f.lat
      ? storyForests().filter((g) => g.id !== id && g.lat && dist(f, g) <= NEAR_KM)
        .sort((a, b) => dist(f, a) - dist(f, b)).slice(0, MAX_LIST - 1).map((g) => g.id)
      : [];
    return { ids: [id, ...near], i: 0 };
  }

  // 이어 들을 이야기가 많은 시·군 (그 시·군 + 60km 안). 처음 한 번만 계산한다.
  let regionCache = null;
  function topRegions(n) {
    if (!regionCache) {
      const names = [...new Set(storyForests().map((f) => f.sigungu).filter(Boolean))];
      regionCache = names.map((k) => { const r = search(k); return [k, r ? r.primary.length + r.nearby.length : 0]; })
        .sort((a, b) => b[1] - a[1]);
    }
    return regionCache.slice(0, n);
  }
  const regionChips = (n) => topRegions(n)
    .map(([k, c]) => `<li><a href="#go/${encodeURIComponent(k)}">${esc(k)} <small>${c}편</small></a></li>`).join("");

  // ---------- 화면 ----------
  function setNav(name) {
    document.querySelectorAll(".top nav a").forEach((a) => {
      if (a.getAttribute("href") === `#${name}`) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  function toneToggle() {
    return `<div class="tone" role="group" aria-label="이야기 말투">
      <button type="button" data-tone="child" aria-pressed="${state.tone === "child"}">아이와 듣기</button>
      <button type="button" data-tone="adult" aria-pressed="${state.tone === "adult"}">어른 해설</button>
    </div>`;
  }

  function bindTone(rerender) {
    main.querySelectorAll("[data-tone]").forEach((b) => b.addEventListener("click", () => {
      state.tone = b.dataset.tone;
      try { localStorage.setItem("tone", state.tone); } catch (e) { /* 무시 */ }
      rerender();
      if (state.idx >= 0) playAt(state.idx);
    }));
  }

  // 홈 화면 사진: 잘라서 보여주므로 변경이 허용된 공공누리 제1유형만 쓴다 (제3·4유형은 변경금지라 숲 화면에서만 원본 비율로)
  const croppable = () => storyForests().filter((f) => f.photo && f.photo.license.includes("제1유형"));
  const HERO_ORDER = ["mf10106ce2", "mf0fcdd4e9", "mf0271855d", "mf74fbdf05", "mf0bb96663"]; // 가로로 잘라도 숲이 잘 보이는 사진
  function heroForest() {
    const ok = new Set(croppable());
    const pool = HERO_ORDER.map((id) => state.byId[id]).filter((f) => ok.has(f));
    const list = pool.length ? pool : croppable();
    if (!list.length) return null;
    const day = Math.floor(Date.now() / 86400000); // 날마다 바뀌고, 하루 안에서는 같은 사진
    return list[day % list.length];
  }
  const small = (f) => esc(f.photo.thumb || f.photo.file); // 홈 화면은 가로 640px 축소본
  const credit = (f) => `사진: ${esc(f.photo.source)} 「${esc(f.photo.title)}」, ${esc(f.photo.license)}`;
  const shortRegion = (f) => [f.sido, f.sigungu].filter(Boolean).join(" ");

  function gallery() {
    const items = croppable();
    if (!items.length) return "";
    const cards = items.map((f) => `<li><a href="#forest/${f.id}">
        <img src="${small(f)}" alt="" loading="lazy" width="640" height="480">
        <span class="g-text"><strong>${esc(cleanName(f.name))}</strong><span>${esc(shortRegion(f))} · 약 ${duration(seconds(f.id))}</span></span>
      </a></li>`).join("");
    // 출처는 카드마다 붙이면 어수선해서 기관별로 모아 한 번에 적는다 (저작물명은 모두 적음)
    const bySource = {};
    for (const f of items) (bySource[f.photo.source] ||= []).push(`「${esc(f.photo.title)}」`);
    const credits = Object.entries(bySource).map(([src, t]) => `${esc(src)} ${t.join(" ")}`).join(", ");
    return `<section class="g-wrap" aria-labelledby="gTitle">
        <h2 class="section-title" id="gTitle">사진으로 먼저 만나는 숲</h2>
        <p class="muted small g-lead">이야기가 있는 숲 가운데 사진이 있는 곳이에요. 누르면 이야기를 들을 수 있어요.</p>
        <ul class="gallery">${cards}</ul>
        <p class="g-credit">사진: ${credits}. 모두 공공누리 제1유형.</p>
      </section>`;
  }

  function viewHome() {
    setNav("");
    const total = storyForests().length;
    const chips = regionChips(8);
    const hero = heroForest();
    main.innerHTML = `
      <form class="ask${hero ? " has-hero" : ""}" id="ask">
        ${hero ? `<div class="hero">
          <img src="${small(hero)}" ${hero.photo.thumb ? `srcset="${small(hero)} 640w, ${esc(hero.photo.file)} 940w" sizes="(min-width: 760px) 720px, 100vw"` : ""}
            alt="${esc(cleanName(hero.name))}의 숲 풍경" width="940" height="626" fetchpriority="high">
          <div class="hero-text"><label for="q">어디로 가세요?</label>
            <span>가는 길에 마을숲 이야기를 들려줄게요</span></div>
        </div>
        <p class="hero-credit"><a href="#forest/${hero.id}">${esc(cleanName(hero.name))}</a> · ${esc(shortRegion(hero))} · ${credit(hero)}</p>`
        : `<label for="q">어디로 가세요?</label>`}
        <div class="ask-row">
          <input id="q" name="q" type="search" autocomplete="off" placeholder="예: 진주, 진도군" enterkeyhint="search">
          <button class="btn" type="submit">숲 이야기 찾기</button>
        </div>
        <p>도착하는 시·군을 적으면, 그 근처 마을숲 이야기를 가까운 순서로 이어서 들려줘요. 한 편은 1분이 채 안 돼요. 도착 15분쯤 전에 틀어 두고, 내리면 이야기에 나온 나무를 아이와 함께 찾아보세요.</p>
        <p><button type="button" class="btn-ghost" id="here">지금 있는 곳 근처 이야기 듣기</button></p>
        <p class="muted small" id="hereMsg" role="status"></p>
      </form>
      ${chips ? `<h2 class="section-title">이어 들을 이야기가 많은 곳</h2><ul class="chips">${chips}</ul>` : ""}
      ${gallery()}
      <section class="about">
      <h2 class="section-title">마을숲이 뭐예요?</h2>
      <p class="prose">마을 사람들이 바람과 물을 막고, 마을을 지켜 달라고 빌며 오랫동안 함께 가꿔 온 숲이에요. 산림청이 전국 ${state.forests.length.toLocaleString()}곳의 역사와 이야기를 조사해 두었는데, 대부분 마을 입구에 조용히 서 있어서 바로 옆을 지나도 모르고 지나치기 쉬워요. ${total ? `그중 기록이 넉넉한 ${total}곳을 아이가 들을 수 있는 이야기로 옮겼어요.` : "지금 이야기를 준비하고 있어요."}</p>
      <p><a class="btn-ghost" href="#map">전국 지도에서 보기</a></p>
      </section>`;
    document.getElementById("ask").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = document.getElementById("q").value.trim();
      if (q) location.hash = `#go/${encodeURIComponent(q)}`;
    });
    bindHere();
  }

  function bindHere() {
    document.getElementById("here").addEventListener("click", () => {
      const msg = document.getElementById("hereMsg");
      if (!navigator.geolocation) { msg.textContent = "이 브라우저에서는 위치를 알 수 없어요. 가는 곳 이름을 적어 주세요."; return; }
      msg.textContent = "위치를 확인하고 있어요…";
      // 위치는 이 휴대폰 안에서 거리 계산에만 쓰고 어디에도 보내지 않는다
      navigator.geolocation.getCurrentPosition(
        (p) => { location.hash = `#near/${p.coords.latitude.toFixed(3)},${p.coords.longitude.toFixed(3)}`; },
        () => { msg.textContent = "위치를 확인하지 못했어요. 위치 권한을 허용하거나, 가는 곳 이름을 적어 주세요."; },
        { timeout: 10000, maximumAge: 300000 });
    });
  }

  const km = (d) => (d < 1 ? "1km 안" : `${Math.round(d)}km`);

  // 목록 한 줄: 이름, 지역·길이·거리, 도착하면 찾아볼 것
  function listItems(ids, center) {
    return ids.map((id, i) => {
      const f = state.byId[id];
      const meta = [region(f), `약 ${duration(seconds(id))}`, center && f.lat ? km(dist(center, f)) : ""].filter(Boolean).join(" · ");
      const find = state.stories[id]?.find || "";
      return `<li data-i="${i}" class="${state.list === ids && state.idx === i ? "now" : ""}"><a href="#forest/${id}">
        <strong>${esc(f.name)}</strong><span>${esc(meta)}${find ? `<br><span class="find-mini">도착하면: ${esc(find)}</span>` : ""}</span></a></li>`;
    }).join("");
  }

  function viewTrip(q) {
    setNav("");
    const r = search(q);
    if (!r) return viewHome();
    renderTrip(r, `#go/${encodeURIComponent(q)}`, () => viewTrip(q));
  }

  function viewNear(arg) {
    setNav("");
    const [lat, lng] = arg.split(",").map(Number);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return viewHome();
    renderTrip(nearSearch({ lat, lng }), `#near/${arg}`, () => viewNear(arg));
  }

  function renderTrip(r, hash, rerender) {
    let ids = [...r.primary, ...r.nearby].map((f) => f.id);
    // 듣는 중인 목록과 같으면 그 목록을 그대로 써서 '듣는 중' 표시가 이어지게 한다
    if (ids.length === state.list.length && ids.every((x, i) => x === state.list[i])) ids = state.list;
    if (!ids.length) {
      const chips = regionChips(8);
      const nearest = r.far || (r.center ? storyForests().filter((f) => f.lat).sort((a, b) => dist(r.center, a) - dist(r.center, b)).slice(0, 3) : []);
      const far = nearest.map((f) => `<li><a href="#forest/${f.id}">${esc(f.name)} · ${esc(f.sigungu || "")} ${km(dist(r.center, f))}</a></li>`).join("");
      const head = r.unknown
        ? `<h1>'${esc(r.label)}', 어디인지 찾지 못했어요</h1>
          <p class="muted">시·군 이름(예: 진주, 진도군)이나 도 이름으로 적어 주세요. 산이나 해수욕장 이름은 아직 알아듣지 못해요.</p>`
        : `<h1>${esc(r.label)} 근처에는 아직 들려줄 이야기가 없어요</h1>
          <p class="muted">${NEAR_KM}km 안에 이야기가 없어요. 전통마을숲 기록은 대부분 남쪽 지역에 있어요. ${far ? "가장 가까운 이야기는 이곳들이에요." : "다른 지역 이름으로 찾아보거나, 아래에서 골라 보세요."}</p>`;
      main.innerHTML = `<div class="trip-head">${head}</div>
        <ul class="chips">${far || chips}</ul>
        <p style="margin-top:22px">${r.here ? "" : `<button type="button" class="btn-ghost" id="here">지금 있는 곳 근처로 찾기</button> `}<a class="btn-ghost" href="#map">전국 지도에서 보기</a> <a class="btn-ghost" href="#">다시 찾기</a></p>
        <p class="muted small" id="hereMsg" role="status"></p>`;
      if (!r.here) bindHere();
      return;
    }
    const note = r.here
      ? `<p class="muted">지금 있는 곳에서 ${NEAR_KM}km 안의 이야기를 가까운 순서로 모았어요. 거리는 직선거리예요.</p>`
      : !r.primary.length
        ? `<p class="muted">${esc(r.label)}에는 아직 이야기가 없어서, ${NEAR_KM}km 안의 가까운 숲 이야기를 모았어요.</p>`
        : r.nearby.length ? `<p class="muted">${esc(r.label)} 이야기 ${r.primary.length}편에 ${NEAR_KM}km 안의 가까운 숲 이야기 ${r.nearby.length}편을 가까운 순서로 더했어요.</p>` : "";
    const title = r.byName ? `'${esc(r.label)}' 숲 이야기`
      : r.here ? `지금 있는 곳 근처, 숲 이야기 ${ids.length}편` : `${esc(r.label)} 가는 길, 숲 이야기 ${ids.length}편`;
    state.trip = ids;
    state.tripBack = { hash, title };
    main.innerHTML = `
      <div class="trip-head"><h1>${title}</h1>${note}</div>
      <button type="button" class="play-all" id="playAll"></button>
      ${toneToggle()}
      <ol class="list" id="list">${listItems(ids, r.center)}</ol>
      <p class="muted small" style="margin-top:14px">숲 이름을 누르면 이야기 글과 길찾기가 나와요.</p>`;
    updatePlayAll();
    document.getElementById("playAll").addEventListener("click", () => {
      if (state.list === ids && state.idx >= 0) togglePause(); // 듣는 중이면 멈춤/이어 듣기
      else startList(ids, 0);
    });
    bindTone(rerender);
  }

  // 목록 화면의 큰 버튼: 듣기 전 / 듣는 중 / 멈춤 상태를 보여준다
  function updatePlayAll() {
    const btn = document.getElementById("playAll");
    if (!btn) return;
    const ids = state.trip;
    const one = ids.length === 1;
    if (state.list === ids && state.idx >= 0) {
      const paused = isPaused();
      btn.innerHTML = `<span class="disc" aria-hidden="true">${paused ? "▶" : "❚❚"}</span>
        <span><strong>${paused ? "멈췄어요" : "듣는 중"}${one ? "" : ` (${state.idx + 1}/${ids.length})`}</strong><span>${esc(state.byId[ids[state.idx]].name)} · 누르면 ${paused ? "이어서 들어요" : "잠시 멈춰요"}</span></span>`;
      return;
    }
    btn.innerHTML = `<span class="disc" aria-hidden="true">▶</span>
      <span><strong>${one ? "이야기 듣기" : "처음부터 이어서 듣기"}</strong><span>${one ? "" : "모두 "}약 ${total(ids)}, 화면을 꺼도 계속 들려줘요.${one ? "" : " 도착 전에 틀어 두세요"}</span></span>`;
  }

  function directions(f) {
    const name = cleanName(f.name);
    const kakao = f.lat
      ? `https://map.kakao.com/link/to/${encodeURIComponent(name)},${f.lat},${f.lng}`
      : `https://map.kakao.com/link/search/${encodeURIComponent(`${f.sigungu || ""} ${name}`.trim())}`;
    const naver = `https://map.naver.com/p/search/${encodeURIComponent(`${f.sigungu || ""} ${name}`.trim())}`;
    // 근처 카페는 우리 데이터로 넣지 않고 지도 검색으로만 연결한다 (폐업 가게 등 검증 못 하는 정보라서).
    // 주소에서 읍·면·동까지만 쓰고, 없으면 시·군까지.
    const parts = (f.address || "").split(/\s+/).filter(Boolean);
    const upto = parts.findIndex((w) => /[읍면동]$/.test(w));
    const area = upto >= 0 ? parts.slice(0, upto + 1).join(" ") : [f.sido, f.sigungu].filter(Boolean).join(" ");
    const cafe = area ? `https://map.kakao.com/link/search/${encodeURIComponent(`${area} 카페`)}` : "";
    return `<a class="btn-ghost" href="${kakao}" target="_blank" rel="noopener">카카오맵으로 길찾기</a>
      <a class="btn-ghost" href="${naver}" target="_blank" rel="noopener">네이버 지도에서 보기</a>${cafe ? `
      <a class="btn-ghost" href="${cafe}" target="_blank" rel="noopener">근처 카페 찾기</a>` : ""}`;
  }

  // 숲 사진: 관광공사 사진 중 숲이 찍힌 걸 사람이 확인한 것만 (pipeline/photos.py).
  // 공공누리 제3·4유형(변경금지)이 있어서 자르지 않고 원본 비율 그대로 보여준다.
  function photoBlock(f) {
    if (!f.photo) return "";
    return `<figure class="photo"><img src="${esc(f.photo.file)}" alt="${esc(f.photo.title)} 사진" loading="lazy">
      <figcaption>사진: ${esc(f.photo.source)} 「${esc(f.photo.title)}」, ${esc(f.photo.license)}</figcaption></figure>`;
  }

  function originBlock(f) {
    const cut = `<span class="cut"> (산림청 기록이 여기서 끊겨 있어요)</span>`;
    return `<details class="origin"><summary>산림청 원문 기록 보기</summary><dl>
      <dt>숲 이름</dt><dd>${esc(f.name)}</dd>
      <dt>소재지</dt><dd>${esc(f.address)}</dd>
      <dt>주요 나무</dt><dd>${esc(f.species || "기록 없음")}</dd>
      <dt>역사 조사 내용</dt><dd>${esc(f.history || "기록 없음")}${f.history && f.cut ? cut : ""}</dd>
      <dt>문화 조사 내용</dt><dd>${esc(f.culture || "기록 없음")}</dd>
    </dl>${f.cut ? `<p class="note">산림청 기록이 중간에 끊겨 있는 숲이에요. 이야기는 끊긴 부분을 짐작해서 잇지 않고, 남아 있는 내용만으로 만들었어요.</p>` : ""}</details>`;
  }

  function viewForest(id) {
    setNav("");
    const f = state.byId[id];
    if (!f) { main.innerHTML = `<p>찾는 숲이 없어요. <a href="#">처음으로</a></p>`; return; }
    const st = state.stories[id];
    if (!st) {
      main.innerHTML = `<div class="forest-head"><h1>${esc(f.name)}</h1><p>${esc(region(f) || f.address)}</p></div>${photoBlock(f)}
        <p class="find"><small>이 숲은</small>아직 기록된 이야기가 적어서 들려줄 이야기를 만들지 못했어요.</p>
        <div class="go">${directions(f)}</div>${originBlock(f)}`;
      return;
    }
    const sents = st[state.tone];
    const paras = [];
    for (let i = 0; i < sents.length; i += 2) paras.push(sents.slice(i, i + 2).map((s) => esc(s.t)).join(" "));
    const trees = (f.trees || []).map((t) => `<li><b>${esc(t.name)}</b> ${esc(t.note)}</li>`).join("");
    const q = queueFrom(id);
    const rest = q.ids.slice(q.i + 1);
    const next = rest.length
      ? `<br>끝나면 가까운 숲 이야기 ${rest.length}편이 이어져요 (모두 약 ${total(q.ids.slice(q.i))})`
      : "<br>근처에 이어 들을 이야기가 아직 없어서 이 한 편만 들려줘요";
    // 여행 목록에서 들어왔으면 목록으로 돌아가는 길 (title 은 renderTrip 에서 이미 esc 처리됨)
    const back = state.tripBack && state.trip.includes(id)
      ? `<p class="back"><a href="${state.tripBack.hash}">← ${state.tripBack.title}</a></p>` : "";
    main.innerHTML = `${back}
      <div class="forest-head"><h1>${esc(f.name)}</h1><p>${esc(region(f) || f.address)}</p></div>
      ${photoBlock(f)}
      ${toneToggle()}
      <div class="listen"><button type="button" class="btn-round" id="playOne" aria-label="이 이야기부터 듣기">▶</button>
        <span class="muted">${state.tone === "child" ? "아이와 듣기" : "어른 해설"}, 약 ${duration(seconds(id))}${next}</span></div>
      <div class="story">${paras.map((p) => `<p>${p}</p>`).join("")}</div>
      <p class="find"><small>도착하면 찾아볼 것</small>${esc(st.find)}</p>
      <div class="go">${directions(f)}</div>
      ${trees ? `<h2 class="section-title">이 숲의 나무</h2><ul class="trees">${trees}</ul><p class="note">나무 설명: 산림청 「숲에 사는 식물 정보」</p>` : ""}
      ${originBlock(f)}
      <p class="note">${st.status === "template"
        ? "이 숲은 AI가 쓴 이야기가 검증을 통과하지 못해서, 산림청 기록을 거의 그대로 들려드려요."
        : `산림청 조사 기록을 바탕으로 AI가 다시 쓴 이야기예요. 원문에 없는 내용이 들어가지 않았는지 ${state.report?.human_review ? "자동 검증과 사람 검수를 거쳤어요" : "원문과 대조해 검증했어요"}. 음성은 AI 음성이에요.`}</p>`;
    document.getElementById("playOne").addEventListener("click", () => startList(q.ids, q.i));
    bindTone(() => viewForest(id));
  }

  let map = null;
  function viewMap() {
    setNav("map");
    const pts = state.forests.filter((f) => f.lat);
    main.innerHTML = `<div class="prose"><h1>전국 마을숲 지도</h1>
      <p>산림청 기록에 있는 마을숲 ${state.forests.length.toLocaleString()}곳 중 위치를 찾은 ${pts.length.toLocaleString()}곳이에요. 진한 점은 들려줄 이야기가 있는 숲이에요.</p></div>
      ${pts.length ? `<div id="mapbox" role="region" aria-label="마을숲 지도"></div>
      <div class="legend"><span><i class="dot on"></i>이야기 있는 숲</span><span><i class="dot off"></i>기록이 적은 숲</span></div>`
      : `<p class="find">마을숲 데이터에는 좌표가 없어서 주소로 위치를 찾는 중이에요. 준비되면 여기에 지도가 나와요.</p>`}`;
    if (!pts.length || !window.L) return;
    if (map) { map.remove(); map = null; }
    map = L.map("mapbox", { scrollWheelZoom: false }).setView([36.0, 127.8], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "© OpenStreetMap 기여자",
    }).addTo(map);
    const sorted = [...pts].sort((a, b) => Number(!!state.stories[a.id]) - Number(!!state.stories[b.id]));
    for (const f of sorted) {
      const has = !!state.stories[f.id];
      L.circleMarker([f.lat, f.lng], has
        ? { radius: 7, color: "#24451c", weight: 1, fillColor: "#3f6d32", fillOpacity: 0.9 }
        : { radius: 4, color: "#7d8c80", weight: 1.5, fillOpacity: 0 })
        .bindPopup(`<b>${esc(f.name)}</b><br>${esc(region(f))}<br><a href="#forest/${f.id}">${has ? "이야기 듣기" : "기록 보기"}</a>`)
        .addTo(map);
    }
  }

  function viewData() {
    setNav("data");
    const r = state.report;
    if (!r) { main.innerHTML = `<p>데이터 리포트를 불러오지 못했어요.</p>`; return; }
    const d = r.diagnosis, g = r.geocode, v = r.verify, h = r.human_review;
    const geoOk = g ? g.address + g.address_village + g.keyword + g.override : null;
    main.innerHTML = `<article class="prose">
      <h1>전통마을숲 데이터, 직접 써보니</h1>
      <p>이 서비스를 만들면서 산림청 전통마을숲 데이터 ${d.records.toLocaleString()}건을 하나하나 정리했어요. 쓰면서 막혔던 점을 숫자와 함께 남겨요. 산림청에도 같은 내용을 개선 의견으로 냈어요.</p>

      <h2>글이 150자 근처에서 잘려 있어요</h2>
      <span class="figure">${d.truncated.history + (d.truncated.culture || 0)}개</span>
      <p>역사·문화 조사 글이 한글 인코딩 기준 253~254바이트에서 끊겨 있어요. 이렇게 끝나는 글 중 마침표로 끝나는 건 ${d.truncated_end_with_period}개뿐이고, 나머지는 문장 중간에서 끊겨요. 원본 DB 칸이 255바이트로 잡혀 있는 것 같아요. 함께 쓴 식물 정보도 이야기 설명 ${d.plants}건이 모두 50바이트 안팎에서 잘려 있어요.</p>

      <h2>위치가 좌표 없이 주소 글자로만 있어요</h2>
      <p>'위치도'라는 이름과 달리 위도·경도가 없어서, 지도에 올리려면 주소로 위치를 따로 찾아야 해요. 주소도 '전북'처럼 줄여 쓴 것이 ${d.address_issues["시도 약칭"] || 0}건, 시·군이 빠진 것이 ${d.address_issues["시군구 없음"] || 0}건, 시도가 없는 것이 ${d.address_issues["시도 없음"] || 0}건이에요.${g ? ` 그래서 주소를 정리해 ${geoOk.toLocaleString()}곳의 위치를 찾았고, ${g.fail}곳은 찾지 못했어요.` : ""}</p>

      <h2>빈 칸이 공백 한 칸으로 와요</h2>
      <p>역사 조사 내용은 ${d.empty_pct.history}%, 문화 조사 내용은 ${d.empty_pct.culture}%가 비어 있어요. 그런데 빈 값이 공백 한 칸으로 들어 있어서, 그냥 세면 비어 있지 않은 것처럼 보여요.</p>

      <h2>다른 숲인데 설명이 같아요</h2>
      <p>설명 글이 완전히 같은 묶음이 ${d.dup_groups}개, ${d.dup_records}건 있어요. 어느 숲의 이야기인지 알 수 없어서 이야기로 만들지 않았어요.</p>

      <h2>그 밖에</h2>
      <p>면적 값(중앙값 ${d.area_median}, 최대 ${d.area_max})이 명세의 단위 표기와 맞지 않아 보여 서비스에는 보여주지 않았어요. 글 중간에 '?'로 깨진 글자가 섞인 기록이 ${d.question_mark_corruption}건, 이름으로 보기 어려운 숲 이름이 ${d.bad_names.length}건 있어요. API는 XML 형식만 제공하고, 식물 정보 파일은 CP949 인코딩이라 일부 프로그램에서 한글이 깨져요.</p>

      <h2>이야기는 이렇게 검증했어요</h2>
      <p>기록이 넉넉하고 중복이 아닌 ${d.story_candidates}곳을 골라 이야기로 만들었어요. 모든 이야기는 숫자와 이름, 근거 문장이 원문에 실제로 있는지 프로그램으로 대조하고, 이야기를 쓴 AI와 별도로 사실 여부를 다시 판정했어요.${v ? ` ${v.stories}편 중 ${v.verified}편이 통과했고, 통과하지 못한 ${v.template}편은 산림청 기록을 거의 그대로 들려줘요.` : ""}${h ? ` 이야기를 만들지 않은 팀원이 ${h.reviewed}편을 원문과 나란히 놓고 다시 검수했어요(통과 ${h.pass}, 수정 ${h.revise}, 탈락 ${h.reject}).` : ""}</p>
      <p><a href="#kit">이 문제들을 미리 정리해 둔 데이터와 코드는 개발자 키트에 있어요.</a></p>
    </article>`;
  }

  function viewKit() {
    setNav("kit");
    const gh = CFG.githubUrl;
    main.innerHTML = `<article class="prose">
      <h1>개발자 키트</h1>
      <p>전통마을숲 데이터를 쓰고 싶은 분이 우리가 겪은 수고를 반복하지 않도록, 정리한 데이터와 코드를 공개해요. 원본 데이터의 이용허락범위는 '제한 없음'이에요.</p>
      <h2>바로 쓰는 데이터</h2>
      <ul class="files">
        <li><a href="kit/maeulsup_clean.csv" download>maeulsup_clean.csv</a><br><span class="muted small">엑셀·구글 시트에서 바로 열리는 UTF-8 CSV</span></li>
        <li><a href="kit/maeulsup_clean.json" download>maeulsup_clean.json</a><br><span class="muted small">프로그램에서 쓰기 좋은 JSON</span></li>
        ${state.report && state.report.geocode ? `<li><a href="kit/maeulsup_clean.geojson" download>maeulsup_clean.geojson</a><br><span class="muted small">지도에 바로 올리는 GeoJSON (위치를 찾은 숲만)</span></li>` : ""}
      </ul>
      <h2>원본과 무엇이 다른가요</h2>
      <p>공백 한 칸으로 오던 빈 값을 진짜 빈 값(null)으로 바꾸고, 시도 표기를 통일하고 시·군을 따로 뽑았어요. 주소로 찾은 위도·경도와 찾은 방법을 붙였고, 글이 잘렸는지(<code>history_truncated</code>), 다른 숲과 설명이 같은지(<code>dup_group</code>)도 표시했어요. 원문 글은 손대지 않고 그대로 두었어요.</p>
      <h2>원본 API를 직접 부르려면</h2>
<pre><code>from urllib.parse import unquote
import requests
# 인증키를 unquote 하지 않으면 requests가 한 번 더 인코딩해서 인증 오류가 나요.
key = unquote("공공데이터포털_인증키")
r = requests.get("활용명세의_요청주소", params={"serviceKey": key, "pageNo": 1, "numOfRows": 100})
print(r.text[:500])  # XML로 와요</code></pre>
      ${gh ? `<p>필드 설명표, 예제 코드, 정리 과정 전체는 <a href="${esc(gh)}" target="_blank" rel="noopener">GitHub 저장소</a>에 있어요.</p>` : ""}
    </article>`;
  }

  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h.startsWith("go/")) viewTrip(h.slice(3));
    else if (h.startsWith("near/")) viewNear(h.slice(5));
    else if (h.startsWith("forest/")) viewForest(h.slice(7));
    else if (h === "map") viewMap();
    else if (h === "data") viewData();
    else if (h === "kit") viewKit();
    else viewHome();
    window.scrollTo(0, 0);
  }

  // ---------- 플레이어 ----------
  const P = {
    box: document.getElementById("player"),
    title: document.getElementById("playerTitle"),
    count: document.getElementById("playerCount"),
    toggle: document.getElementById("playerToggle"),
    next: document.getElementById("playerNext"),
    stop: document.getElementById("playerStop"),
    bar: document.getElementById("playerBar"),
  };

  function startList(ids, i) {
    state.list = ids;
    playAt(i);
  }

  // 마을숲은 대부분 시골이라 가는 길에 신호가 끊기기 쉽다. 듣기 시작하면 남은 음성을 차례로 미리 받아 둔다.
  const blobs = {}, loading = new Set();
  const audioSrc = (id) => state.stories[id]?.audio?.[state.tone] || state.stories[id]?.audio?.child;
  async function prefetchList(ids, from) {
    const tone = state.tone;
    for (const id of ids.slice(from)) {
      if (state.list !== ids || state.tone !== tone) return; // 다른 목록이나 말투로 바뀌면 그만
      const src = audioSrc(id);
      if (!src || blobs[src] || loading.has(src)) continue;
      loading.add(src);
      try {
        const r = await fetch(src);
        if (r.ok) blobs[src] = URL.createObjectURL(await r.blob());
      } catch (e) { return; } // 신호가 없으면 다음 이야기로 넘어갈 때 다시 시도
      finally { loading.delete(src); }
    }
  }

  function markNow() {
    document.querySelectorAll("#list li").forEach((li) => li.classList.toggle("now", Number(li.dataset.i) === state.idx));
    updatePlayAll();
  }

  const isPaused = () => (state.speaking ? speechSynthesis.paused : audio.paused);

  // 재생/멈춤 버튼 모양을 실제 상태에 맞춘다 (잠금화면·블루투스 버튼으로 멈춘 경우도)
  function syncToggle() {
    if (state.idx < 0) return;
    const paused = isPaused();
    P.toggle.textContent = paused ? "▶" : "❚❚";
    P.toggle.setAttribute("aria-label", paused ? "이어 듣기" : "일시정지");
    updatePlayAll();
  }

  function togglePause() {
    if (state.idx < 0) { if (state.list.length) playAt(0); return; } // 다 들은 뒤에는 처음부터 다시
    const paused = isPaused();
    if (state.speaking) paused ? speechSynthesis.resume() : speechSynthesis.pause();
    else paused ? audio.play() : audio.pause();
    setTimeout(syncToggle, 0);
  }

  function playAt(i) {
    stopSpeech();
    if (i >= state.list.length) { finish(true); return; }
    state.idx = i;
    const id = state.list[i];
    const f = state.byId[id];
    const st = state.stories[id];
    P.box.hidden = false;
    P.title.textContent = f.name;
    P.count.textContent = state.list.length > 1 ? `${i + 1} / ${state.list.length}` : region(f);
    P.toggle.textContent = "❚❚";
    P.toggle.setAttribute("aria-label", "일시정지");
    P.next.hidden = state.list.length <= 1 || i === state.list.length - 1;
    P.bar.style.width = "0";
    markNow();
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({ title: f.name, artist: region(f), album: "마을숲, 어디까지 들어봤니?" });
    }
    const src = audioSrc(id);
    if (src) {
      audio.src = blobs[src] || src;
      prefetchList(state.list, i + 1);
      audio.play().catch(() => speak(id));
    } else {
      speak(id);
    }
  }

  // 음성 파일이 없을 때만 브라우저 음성으로 읽는다 (화면이 꺼지면 멈출 수 있음)
  function speak(id) {
    if (!("speechSynthesis" in window)) { P.title.textContent += " (이 기기에서는 음성을 낼 수 없어요)"; return; }
    const text = storyText(id, state.tone) + (state.tone === "child" ? " " + state.stories[id].find : "");
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = 0.95;
    u.onend = () => { if (state.speaking) { state.speaking = false; playAt(state.idx + 1); } };
    state.speaking = true;
    speechSynthesis.speak(u);
  }
  function stopSpeech() {
    state.speaking = false;
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  // done: 목록을 끝까지 들었을 때. 플레이어를 바로 닫지 않고 다 들었다고 알려준다.
  function finish(done) {
    state.idx = -1;
    markNow();
    if (!done) { P.box.hidden = true; return; }
    P.count.textContent = state.list.length > 1 ? `${state.list.length}편을 다 들었어요` : "다 들었어요";
    P.title.textContent = "도착하면 함께 찾아봐요";
    P.toggle.textContent = "↻";
    P.toggle.setAttribute("aria-label", "처음부터 다시 듣기");
    P.next.hidden = true;
    P.bar.style.width = "100%";
  }

  audio.addEventListener("ended", () => playAt(state.idx + 1));
  audio.addEventListener("timeupdate", () => {
    if (audio.duration) P.bar.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
  });
  audio.addEventListener("play", syncToggle);
  audio.addEventListener("pause", syncToggle);
  P.toggle.addEventListener("click", togglePause);
  P.next.addEventListener("click", () => playAt(state.idx + 1));
  P.title.parentElement.addEventListener("click", () => {
    if (state.idx >= 0) location.hash = `#forest/${state.list[state.idx]}`;
  });
  P.stop.addEventListener("click", () => { audio.pause(); stopSpeech(); finish(false); });
  if ("mediaSession" in navigator) {
    navigator.mediaSession.setActionHandler("nexttrack", () => { if (state.idx >= 0) playAt(state.idx + 1); });
    navigator.mediaSession.setActionHandler("previoustrack", () => { if (state.idx >= 0) playAt(Math.max(0, state.idx - 1)); });
    navigator.mediaSession.setActionHandler("play", () => audio.play());
    navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  }

  // ---------- 시작 ----------
  window.addEventListener("hashchange", route);
  load().then(route).catch(() => {
    main.innerHTML = `<p>숲 기록을 불러오지 못했어요. 인터넷 연결을 확인하고 새로고침해 주세요.</p>`;
  });
})();

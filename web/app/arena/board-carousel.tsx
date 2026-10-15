"use client";

import {useRef, useState, type KeyboardEvent, type PointerEvent} from "react";
import {makeT, screenshotPath, type IntroLanguage} from "./locale";

type Board = {
  id: string;
  name: string;
  scope: string;
  players: string;
  alt: string;
};

export function BoardCarousel({boards, basePath, lang}: {boards: readonly Board[]; basePath: string; lang: IntroLanguage}) {
  const t = makeT(lang);
  const asset = (id: string) => screenshotPath(basePath, id, lang);
  const [selected, setSelected] = useState(0);
  const gesture = useRef<{id: number; x: number; y: number} | null>(null);
  const suppressClick = useRef(false);
  const previousButton = useRef<HTMLButtonElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const current = boards[selected];
  const move = (direction: number) => setSelected(index => (index + direction + boards.length) % boards.length);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      move(event.key === "ArrowLeft" ? -1 : 1);
    }
  }

  function startGesture(event: PointerEvent<HTMLDivElement>) {
    suppressClick.current = false;
    if (!event.isPrimary || event.button !== 0) return;
    gesture.current = {id: event.pointerId, x: event.clientX, y: event.clientY};
  }

  function trackGesture(event: PointerEvent<HTMLDivElement>) {
    const start = gesture.current;
    if (!start || start.id !== event.pointerId) return;
    const dx = Math.abs(event.clientX - start.x);
    const dy = Math.abs(event.clientY - start.y);
    if (dx > 10 || dy > 10) suppressClick.current = true;
    if (dx > 10 && dx > dy * 1.25) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  }

  function finishGesture(event: PointerEvent<HTMLDivElement>) {
    const start = gesture.current;
    gesture.current = null;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) >= 45 && Math.abs(dx) > Math.abs(dy) * 1.25) {
      suppressClick.current = true;
      (dx < 0 ? nextButton : previousButton).current?.focus({preventScroll: true});
      move(dx < 0 ? 1 : -1);
    }
  }

  return <section className="board-carousel" aria-label={t("Live board screenshots", "实时牌桌截图")} aria-roledescription={t("carousel", "轮播")}>
    <div className="carousel-topline"><span className="eyebrow">{t("At the table", "走上牌桌")}</span><span>{t("10 games / real interfaces", "10 款游戏 / 真实操作界面")}</span></div>
    <div className="board-stage" onPointerDown={startGesture} onPointerMove={trackGesture}
      onPointerUp={finishGesture} onPointerCancel={() => { gesture.current = null; }}
      onPointerLeave={event => { if (!event.currentTarget.hasPointerCapture(event.pointerId)) gesture.current = null; }}
      onClickCapture={event => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; } }}>
      {boards.map((board, index) => {
        const distance = (index - selected + boards.length) % boards.length;
        const position = distance === 0 ? "active" : distance === 1 ? "next" : distance === boards.length - 1 ? "previous" : "hidden";
        return <div className="board-slide" key={board.id} data-position={position}
          role="group" aria-roledescription={t("slide", "幻灯片")} aria-label={t(`${index + 1} of ${boards.length}: ${board.name}`, `第 ${index + 1} 张，共 ${boards.length} 张：${board.name}`)}
          aria-hidden={index !== selected}>
          <a href={asset(board.id)} target="_blank" rel="noreferrer" draggable={false}
            tabIndex={index === selected ? 0 : -1} aria-label={t(`Open the full ${board.name} screenshot`, `查看${board.name}完整截图`)}>
            {/* These small JPEGs are served directly by GitHub Pages, without an image server. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={asset(board.id)} alt={board.alt} width="1280" height="720"
              draggable={false} loading={position === "hidden" ? "lazy" : "eager"} fetchPriority={index === 0 ? "high" : "low"}/>
          </a>
        </div>;
      })}
    </div>
    <div className="carousel-caption">
      <button ref={previousButton} type="button" className="carousel-arrow" onClick={() => move(-1)} onKeyDown={onKeyDown}
        aria-label={t("Previous game", "上一款游戏")}><span aria-hidden="true">←</span></button>
      <div className="carousel-current" aria-live="polite" aria-atomic="true">
        <span className="carousel-count">{String(selected + 1).padStart(2, "0")} / {String(boards.length).padStart(2, "0")}</span>
        <h2>{current.name}</h2><p>{current.scope} · {current.players}{t(" players", " 人")}</p>
      </div>
      <button ref={nextButton} type="button" className="carousel-arrow" onClick={() => move(1)} onKeyDown={onKeyDown}
        aria-label={t("Next game", "下一款游戏")}><span aria-hidden="true">→</span></button>
    </div>
    <div className="carousel-dots" role="group" aria-label={t("Choose a live board", "选择游戏牌桌")}>
      {boards.map((board, index) => <button key={board.id} type="button" aria-label={t(`Show ${board.name}`, `展示${board.name}`)}
        aria-pressed={index === selected} onClick={() => setSelected(index)}><span/></button>)}
    </div>
    <p className="carousel-hint">{t("Arrows or swipe to explore · Click the board for full size", "点击箭头或左右滑动切换 · 点击棋盘查看原图")}</p>
  </section>;
}

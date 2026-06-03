import { useAppStore } from "../store/appStore";

export function PoiDetailPanel() {
  const poi = useAppStore((s) => s.detailPoi);
  const setSelectedPoi = useAppStore((s) => s.setSelectedPoi);

  if (!poi) return null;

  return (
    <aside className="poi-detail-panel">
      <div className="poi-detail-panel__head">
        <div>
          <span className="panel-kicker">{poi.type}</span>
          <h2>{poi.name}</h2>
          <span className={["poi-comment-badge", poi.commentParsed ? "poi-comment-badge--ready" : "poi-comment-badge--missing"].join(" ")}>
            {poi.commentParsed ? "已解析评论" : "未解析评论"}
          </span>
        </div>
        <button type="button" className="btn-secondary" onClick={() => setSelectedPoi(null)}>关闭</button>
      </div>
      <p className="poi-detail-panel__meta">评分 {poi.rating}｜人均 ¥{poi.avgPrice}｜预计排队 {poi.queueTime} 分钟｜建议停留 {poi.recommendedStayTime} 分钟</p>
      <div className="poi-tags">{poi.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      <section>
        <h3>评价总结</h3>
        <ul>{poi.reviewSummary.map((text) => <li key={text}>{text}</li>)}</ul>
      </section>
      <section>
        <h3>风险提醒</h3>
        <ul>{poi.riskNotes.map((text) => <li key={text}>{text}</li>)}</ul>
      </section>
      <section>
        <h3>为什么推荐</h3>
        <p>{poi.recommendReason}</p>
      </section>
    </aside>
  );
}

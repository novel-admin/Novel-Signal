import { IntelligencePage } from "../../components/IntelligencePage";

export default function ScorecardsPage() {
  return <IntelligencePage eyebrow="S9 · Evidence-backed comparison" title="Scorecards"
    description="See where each SKU leads, competes, lags, or remains unknown because required evidence is missing or stale."
    endpoint="/scorecards" empty="No scorecards have been calculated."
    columns={[{key:"entity_id",label:"SKU"},{key:"dimension",label:"Dimension"},{key:"score",label:"Score"},{key:"band",label:"Band"},{key:"freshness_state",label:"Freshness"},{key:"confidence",label:"Confidence"},{key:"unknown_reason",label:"Unknown reason"}]} />;
}

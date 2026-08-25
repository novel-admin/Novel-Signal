import { IntelligencePage } from "../../components/IntelligencePage";

export default function AdsPage() {
  return <IntelligencePage eyebrow="S4 · Measured and derived" title="Ad intelligence"
    description="Compare sampled competitor sponsored presence with Novel-owned advertising performance. Missing captures are not treated as absence."
    endpoint="/ads/observations" empty="No published sponsored observations are available."
    columns={[{key:"captured_at",label:"Observed"},{key:"competitor_id",label:"Competitor"},{key:"keyword_id",label:"Keyword"},{key:"sponsored_position",label:"Position"},{key:"confidence",label:"Confidence"},{key:"evidence_ref",label:"Evidence"}]} />;
}

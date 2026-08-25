import { IntelligencePage } from "../../components/IntelligencePage";

export default function ReviewsPage() {
  return <IntelligencePage eyebrow="S7 · Published evidence only" title="Review intelligence"
    description="Inspect ratings, review evidence, topics, and confidence without exposing reviewer identity."
    endpoint="/reviews" empty="No published review observations are available."
    columns={[{key:"published_on",label:"Published"},{key:"target_id",label:"Product"},{key:"rating",label:"Rating"},{key:"topic_type",label:"Theme"},{key:"confidence",label:"Confidence"},{key:"raw_capture_id",label:"Evidence"}]} />;
}

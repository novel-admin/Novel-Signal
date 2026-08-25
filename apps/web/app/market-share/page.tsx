import { IntelligencePage } from "../../components/IntelligencePage";

export default function MarketSharePage() {
  return <IntelligencePage eyebrow="S8 · Estimated ranges" title="Market share"
    description="View guarded unit and revenue ranges. Estimates are withheld when evidence or model quality is insufficient."
    endpoint="/market-share/estimates" empty="No supported estimates are available."
    columns={[{key:"observed_on",label:"Date"},{key:"entity_id",label:"Entity"},{key:"units_low",label:"Units low"},{key:"units_point",label:"Units estimate"},{key:"units_high",label:"Units high"},{key:"confidence",label:"Confidence"},{key:"model_version",label:"Model"}]} />;
}

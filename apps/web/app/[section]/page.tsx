import { notFound } from "next/navigation";

const sections: Record<string, string> = {
  universe: "Competitors, Novel products, competitor products, and battle cards.",
  keywords: "Priority keywords, tracking targets, cadence, and rank history.",
  products: "Listing, price, offer, and availability observations.",
  sources: "Amazon APIs, Google Search Console, Meta APIs, and competitor collection status.",
  changes: "Evidence-backed changes from valid consecutive observations.",
  actions: "Owned work created from important changes.",
  operations: "Collection jobs, freshness, failures, and quarantine.",
};

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const description = sections[section];
  if (!description) notFound();

  return (
    <>
      <div className="eyebrow">Scaffolded module</div>
      <h1>{section[0].toUpperCase() + section.slice(1)}</h1>
      <p className="lede">{description}</p>
      <div className="card" style={{ marginTop: 36 }}>
        <span>Implementation status</span>
        <strong>Ready to build</strong>
      </div>
    </>
  );
}

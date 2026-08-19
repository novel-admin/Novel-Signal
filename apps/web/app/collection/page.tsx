import CollectionClient from "./collection-client";

export default function CollectionPage() {
  return (
    <>
      <div className="eyebrow">S12 · Collection infrastructure</div>
      <h1>Collection</h1>
      <p className="lede">
        Monitor collection jobs, raw evidence, parser quality, quarantine,
        runtime readiness and retention.
      </p>
      <CollectionClient />
    </>
  );
}

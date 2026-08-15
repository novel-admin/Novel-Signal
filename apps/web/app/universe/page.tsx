import UniverseClient from "./universe-client";

export default function UniversePage() {
  return (
    <>
      <div className="eyebrow">S1 · Universe &amp; competitor setup</div>
      <h1>Universe</h1>
      <p className="lede">
        Configure owned products, competitors, tracked marketplace listings, and direct
        comparison battle cards using live Novel Signal data.
      </p>
      <UniverseClient />
    </>
  );
}

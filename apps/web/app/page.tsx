const cards = [
  ["Tracked keywords", "Not configured"],
  ["Tracked products", "Not configured"],
  ["Collection health", "Waiting for setup"],
];

export default function OverviewPage() {
  return (
    <>
      <div className="eyebrow">Week 1 foundation</div>
      <h1>Competitive watchtower</h1>
      <p className="lede">
        Configure the Amazon.in universe, collect evidence, publish trusted observations,
        detect changes, and assign actions.
      </p>
      <section className="grid">
        {cards.map(([label, value]) => (
          <article className="card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
    </>
  );
}

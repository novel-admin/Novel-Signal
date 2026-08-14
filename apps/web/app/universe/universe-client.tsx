"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiRequest, csvUrl, importCsv, loadUniverse, validateCsv } from "./api";
import type {
  BattleCard,
  Competitor,
  CompetitorProduct,
  CsvValidationResult,
  Product,
  UniverseData,
} from "./types";

type Tab = "competitors" | "products" | "competitor-products" | "battle-cards";
type Entity = Competitor | Product | CompetitorProduct | BattleCard;
type BattleCardBasis = Pick<
  BattleCard["items"][number],
  | "priority_order"
  | "same_pack_basis"
  | "same_price_band"
  | "same_category"
  | "same_use_case"
  | "notes"
>;
type FormValue = string | boolean | string[] | Record<string, BattleCardBasis>;
type FormValues = Record<string, FormValue>;

const tabs: { id: Tab; label: string }[] = [
  { id: "competitors", label: "Competitors" },
  { id: "products", label: "Products" },
  { id: "competitor-products", label: "Competitor products" },
  { id: "battle-cards", label: "Battle cards" },
];

const emptyData: UniverseData = {
  competitors: [],
  products: [],
  competitorProducts: [],
  battleCards: [],
};

function optional(value: string): string | undefined {
  const normalized = value.trim();
  return normalized || undefined;
}

function nullable(value: string, editing: boolean): string | null | undefined {
  return optional(value) ?? (editing ? null : undefined);
}

function optionalNumber(value: string): number | undefined {
  return value.trim() ? Number(value) : undefined;
}

function nullableNumber(value: string, editing: boolean): number | null | undefined {
  return optionalNumber(value) ?? (editing ? null : undefined);
}

function activeItems(card: BattleCard) {
  return card.items.filter((item) => !item.archived_at);
}

export default function UniverseClient() {
  const [activeTab, setActiveTab] = useState<Tab>("competitors");
  const [data, setData] = useState<UniverseData>(emptyData);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Entity | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [csvText, setCsvText] = useState("");
  const [csvFileName, setCsvFileName] = useState("");
  const [csvResult, setCsvResult] = useState<CsvValidationResult | null>(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loadUniverse(includeArchived));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load Universe");
    } finally {
      setLoading(false);
    }
  }, [includeArchived]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const counts = useMemo(
    () => ({
      competitors: data.competitors.length,
      products: data.products.length,
      "competitor-products": data.competitorProducts.length,
      "battle-cards": data.battleCards.length,
    }),
    [data],
  );

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
    setError(null);
  }

  function selectTab(tab: Tab) {
    setActiveTab(tab);
    setCsvText("");
    setCsvFileName("");
    setCsvResult(null);
    setCsvMessage(null);
  }

  async function chooseCsv(file: File | undefined) {
    if (!file) return;
    setCsvFileName(file.name);
    setCsvText(await file.text());
    setCsvResult(null);
    setCsvMessage(null);
  }

  async function runCsvValidation() {
    setCsvBusy(true);
    setCsvMessage(null);
    try {
      setCsvResult(await validateCsv(activeTab, csvText));
    } catch (requestError) {
      setCsvMessage(requestError instanceof Error ? requestError.message : "CSV validation failed");
    } finally {
      setCsvBusy(false);
    }
  }

  async function confirmCsvImport() {
    setCsvBusy(true);
    setCsvMessage(null);
    try {
      const result = await importCsv(activeTab, csvText);
      setCsvMessage(`${result.imported_rows} ${singularLabel(activeTab)} record${result.imported_rows === 1 ? "" : "s"} imported.`);
      setCsvText("");
      setCsvFileName("");
      setCsvResult(null);
      await reload();
    } catch (requestError) {
      setCsvMessage(requestError instanceof Error ? requestError.message : "CSV import failed");
    } finally {
      setCsvBusy(false);
    }
  }

  function openEdit(entity: Entity) {
    setEditing(entity);
    setFormOpen(true);
    setError(null);
  }

  async function mutateState(entity: Entity, archived: boolean) {
    setError(null);
    try {
      const endpoint = tabEndpoint(activeTab);
      await apiRequest(`${endpoint}/${entity.id}/${archived ? "archive" : "restore"}`, {
        method: "POST",
      });
      await reload();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Action failed");
    }
  }

  async function save(values: FormValues) {
    setSaving(true);
    setError(null);
    try {
      const endpoint = tabEndpoint(activeTab);
      const payload = buildPayload(activeTab, values, Boolean(editing));
      await apiRequest(editing ? `${endpoint}/${editing.id}` : endpoint, {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      setFormOpen(false);
      setEditing(null);
      await reload();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save record");
    } finally {
      setSaving(false);
    }
  }

  const records = recordsForTab(activeTab, data);
  const createDisabled =
    (activeTab === "competitor-products" && !data.competitors.some((item) => !item.archived_at)) ||
    (activeTab === "battle-cards" && !data.products.some((item) => !item.archived_at));
  const dependencyHint = activeTab === "competitor-products"
    ? "Create an active competitor first"
    : activeTab === "battle-cards"
      ? "Create an active owned product first"
      : undefined;

  return (
    <section className="universe-panel">
      <div className="universe-toolbar">
        <div className="tabs" role="tablist" aria-label="Universe records">
          {tabs.map((tab) => (
            <button
              className={activeTab === tab.id ? "tab active" : "tab"}
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              role="tab"
              type="button"
            >
              {tab.label}<span className="count">{counts[tab.id]}</span>
            </button>
          ))}
        </div>
        <div className="toolbar-actions">
          <label className="archive-toggle">
            <input
              checked={includeArchived}
              onChange={(event) => setIncludeArchived(event.target.checked)}
              type="checkbox"
            />
            Show archived
          </label>
          <button className="button primary" disabled={createDisabled} onClick={openCreate} title={createDisabled ? dependencyHint : undefined} type="button">
            + Create {singularLabel(activeTab)}
          </button>
        </div>
      </div>

      <div className="csv-toolbar" aria-label="CSV tools">
        <div><strong>CSV tools</strong><span>Validate before importing {activeTab.replaceAll("-", " ")}.</span></div>
        <div className="csv-actions">
          <a className="button" download href={csvUrl(activeTab, "template")}>Download template</a>
          <label className="button file-button">Choose CSV<input accept=".csv,text/csv" onChange={(event) => void chooseCsv(event.target.files?.[0])} type="file" /></label>
          <a className="button" download href={csvUrl(activeTab, "export", includeArchived)}>Export CSV</a>
        </div>
      </div>

      {csvFileName ? <div className="csv-panel">
        <div className="csv-summary"><div><strong>{csvFileName}</strong><span>{csvResult ? `${csvResult.valid_rows}/${csvResult.total_rows} valid rows` : "Ready for dry-run validation"}</span></div>
          <div className="csv-actions"><button className="button" disabled={csvBusy} onClick={() => void runCsvValidation()} type="button">{csvBusy ? "Validating…" : "Run dry-run"}</button>
          <button className="button primary" disabled={csvBusy || !csvResult?.valid} onClick={() => void confirmCsvImport()} title={!csvResult?.valid ? "A successful dry-run is required" : undefined} type="button">Confirm import</button></div>
        </div>
        {csvResult ? <div className={csvResult.valid ? "csv-result valid" : "csv-result invalid"} role="status"><strong>{csvResult.valid ? "Validation passed — zero rows written" : "Validation failed — zero rows written"}</strong><span>{csvResult.total_rows} total · {csvResult.valid_rows} valid · {csvResult.invalid_rows} invalid</span></div> : null}
        {csvResult?.errors.length ? <div className="csv-errors"><table><thead><tr><th>Row</th><th>Field</th><th>Code</th><th>Message</th></tr></thead><tbody>{csvResult.errors.map((item, index) => <tr key={`${item.row}-${item.field}-${index}`}><td>{item.row}</td><td>{item.field}</td><td>{item.code}</td><td>{item.message}</td></tr>)}</tbody></table></div> : null}
        {csvMessage ? <div className="csv-message">{csvMessage}</div> : null}
      </div> : csvMessage ? <div className="csv-message standalone">{csvMessage}</div> : null}

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      {loading ? (
        <div className="loading-state"><span className="spinner" />Loading live Universe data…</div>
      ) : records.length === 0 ? (
        <div className="empty-state">
          <strong>{emptyMessage(activeTab)}</strong>
          <span>Create the first record to begin configuring the Week 1 universe.</span>
          {createDisabled ? <span className="dependency-hint">{dependencyHint}</span> : <button className="button" onClick={openCreate} type="button">Create now</button>}
        </div>
      ) : (
        <UniverseTable
          data={data}
          records={records}
          tab={activeTab}
          onEdit={openEdit}
          onStateChange={mutateState}
        />
      )}

      {formOpen ? (
        <EntityForm
          data={data}
          entity={editing}
          saving={saving}
          tab={activeTab}
          onCancel={() => { setFormOpen(false); setEditing(null); }}
          onSave={save}
        />
      ) : null}
    </section>
  );
}

function tabEndpoint(tab: Tab): string {
  return `/universe/${tab}`;
}

function singularLabel(tab: Tab): string {
  return {
    competitors: "competitor",
    products: "product",
    "competitor-products": "competitor product",
    "battle-cards": "battle card",
  }[tab];
}

function emptyMessage(tab: Tab): string {
  return {
    competitors: "No competitors configured yet",
    products: "No products configured yet",
    "competitor-products": "No competitor products configured yet",
    "battle-cards": "No battle cards configured yet",
  }[tab];
}

function recordsForTab(tab: Tab, data: UniverseData): Entity[] {
  if (tab === "competitors") return data.competitors;
  if (tab === "products") return data.products;
  if (tab === "competitor-products") return data.competitorProducts;
  return data.battleCards;
}

function buildPayload(tab: Tab, values: FormValues, editing: boolean) {
  if (tab === "competitors") {
    return {
      name: values.name,
      parent_company: nullable(String(values.parent_company ?? ""), editing),
      amazon_store_url: nullable(String(values.amazon_store_url ?? ""), editing),
      amazon_seller_id: nullable(String(values.amazon_seller_id ?? ""), editing),
      category_presence: nullable(String(values.category_presence ?? ""), editing),
      positioning_tier: values.positioning_tier,
      threat_rating: nullableNumber(String(values.threat_rating ?? ""), editing),
      analyst_owner: nullable(String(values.analyst_owner ?? ""), editing),
      notes: nullable(String(values.notes ?? ""), editing),
    };
  }
  if (tab === "products") {
    return productPayload(values, true, editing);
  }
  if (tab === "competitor-products") {
    return { competitor_id: values.competitor_id, ...productPayload(values, false, editing) };
  }
  const selected = Array.isArray(values.competitor_product_ids)
    ? values.competitor_product_ids
    : [];
  const savedBasis = isBasisMap(values.item_basis) ? values.item_basis : {};
  return {
    product_id: values.product_id,
    name: values.name,
    status: values.status,
    comparison_notes: nullable(String(values.comparison_notes ?? ""), editing),
    items: selected.map((id, index) => ({
      competitor_product_id: id,
      priority_order: savedBasis[id]?.priority_order ?? index + 1,
      same_pack_basis: savedBasis[id]?.same_pack_basis ?? false,
      same_price_band: savedBasis[id]?.same_price_band ?? false,
      same_category: savedBasis[id]?.same_category ?? false,
      same_use_case: savedBasis[id]?.same_use_case ?? false,
      notes: savedBasis[id]?.notes ?? undefined,
    })),
  };
}

function isBasisMap(value: FormValue | undefined): value is Record<string, BattleCardBasis> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function productPayload(values: FormValues, owned: boolean, editing: boolean) {
  return {
    ...(owned ? { internal_sku: values.internal_sku } : {}),
    name: values.name,
    brand: values.brand,
    category: values.category,
    marketplace: "amazon_in",
    marketplace_product_id: nullable(String(values.marketplace_product_id ?? ""), editing),
    product_url: nullable(String(values.product_url ?? ""), editing),
    pack_quantity: nullableNumber(String(values.pack_quantity ?? ""), editing),
    pack_unit: nullable(String(values.pack_unit ?? ""), editing),
    tracking_tier: values.tracking_tier,
  };
}

function UniverseTable({
  tab,
  records,
  data,
  onEdit,
  onStateChange,
}: {
  tab: Tab;
  records: Entity[];
  data: UniverseData;
  onEdit: (entity: Entity) => void;
  onStateChange: (entity: Entity, archive: boolean) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead><TableHead tab={tab} /></thead>
        <tbody>
          {records.map((record) => (
            <TableRow
              data={data}
              key={record.id}
              record={record}
              tab={tab}
              onEdit={onEdit}
              onStateChange={onStateChange}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableHead({ tab }: { tab: Tab }) {
  const columns = {
    competitors: ["Competitor", "Amazon setup", "Category", "Position", "Owner", "State"],
    products: ["Product", "Amazon identity", "Pack", "Tier", "State"],
    "competitor-products": ["Tracked product", "Competitor", "Amazon identity", "Pack", "Tier", "State"],
    "battle-cards": ["Battle card", "Owned product", "Competitors", "Status", "State"],
  }[tab];
  return <tr>{columns.map((column) => <th key={column}>{column}</th>)}<th>Actions</th></tr>;
}

function TableRow({
  tab,
  record,
  data,
  onEdit,
  onStateChange,
}: {
  tab: Tab;
  record: Entity;
  data: UniverseData;
  onEdit: (entity: Entity) => void;
  onStateChange: (entity: Entity, archive: boolean) => void;
}) {
  const archived = Boolean(record.archived_at);
  let cells: React.ReactNode[];
  if (tab === "competitors") {
    const item = record as Competitor;
    cells = [
      <Primary key="name" title={item.name} detail={item.parent_company} />,
      <Primary key="amazon" title={item.amazon_seller_id ?? "Not set"} detail={item.amazon_store_url ? "Store URL configured" : "No store URL"} />,
      item.category_presence ?? "—",
      <Primary key="position" title={item.positioning_tier} detail={item.threat_rating ? `Threat ${item.threat_rating}/5` : "No threat rating"} />,
      item.analyst_owner ?? "—",
      <StateBadge key="state" archived={archived} />,
    ];
  } else if (tab === "products") {
    const item = record as Product;
    cells = [
      <Primary key="name" title={item.name} detail={`${item.brand} · ${item.internal_sku}`} />,
      <Primary key="amazon" title={item.marketplace_product_id ?? "Not assigned"} detail={item.category} />,
      item.pack_quantity ? `${item.pack_quantity} ${item.pack_unit ?? "units"}` : "—",
      <span className="tier" key="tier">{item.tracking_tier}</span>,
      <StateBadge key="state" archived={archived} />,
    ];
  } else if (tab === "competitor-products") {
    const item = record as CompetitorProduct;
    const competitor = data.competitors.find((candidate) => candidate.id === item.competitor_id);
    cells = [
      <Primary key="name" title={item.name} detail={`${item.brand} · ${item.category}`} />,
      competitor?.name ?? "Unknown competitor",
      item.marketplace_product_id ?? "Not assigned",
      item.pack_quantity ? `${item.pack_quantity} ${item.pack_unit ?? "units"}` : "—",
      <span className="tier" key="tier">{item.tracking_tier}</span>,
      <StateBadge key="state" archived={archived} />,
    ];
  } else {
    const item = record as BattleCard;
    cells = [
      <Primary key="name" title={item.name} detail={item.comparison_notes} />,
      <Primary key="product" title={item.product.name} detail={item.product.internal_sku} />,
      <Primary key="mapped" title={`${activeItems(item).length} mapped`} detail={activeItems(item).map((entry) => entry.competitor_product.name).join(", ")} />,
      <span className={`status ${item.status}`} key="status">{item.status}</span>,
      <StateBadge key="state" archived={archived} />,
    ];
  }
  return (
    <tr className={archived ? "archived-row" : ""}>
      {cells.map((cell, index) => <td key={index}>{cell}</td>)}
      <td><div className="row-actions">
        <button className="text-button" onClick={() => onEdit(record)} type="button">Edit</button>
        <button className="text-button" onClick={() => onStateChange(record, !archived)} type="button">
          {archived ? "Restore" : "Archive"}
        </button>
      </div></td>
    </tr>
  );
}

function Primary({ title, detail }: { title: string; detail?: string | null }) {
  return <div className="primary-cell"><strong>{title}</strong>{detail ? <span>{detail}</span> : null}</div>;
}

function StateBadge({ archived }: { archived: boolean }) {
  return <span className={archived ? "state archived" : "state active"}>{archived ? "Archived" : "Active"}</span>;
}

function EntityForm({
  tab,
  entity,
  data,
  saving,
  onCancel,
  onSave,
}: {
  tab: Tab;
  entity: Entity | null;
  data: UniverseData;
  saving: boolean;
  onCancel: () => void;
  onSave: (values: FormValues) => Promise<void>;
}) {
  const [values, setValues] = useState<FormValues>(() => initialValues(tab, entity));

  function setValue(name: string, value: FormValue) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave(values);
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <form className="entity-modal" onMouseDown={(event) => event.stopPropagation()} onSubmit={submit}>
        <div className="modal-header">
          <div><span className="eyebrow">{entity ? "Edit" : "Create"}</span><h2>{singularLabel(tab)}</h2></div>
          <button aria-label="Close form" className="icon-button" onClick={onCancel} type="button">×</button>
        </div>
        <div className="form-grid"><FormFields data={data} tab={tab} values={values} setValue={setValue} /></div>
        <div className="modal-actions">
          <button className="button" disabled={saving} onClick={onCancel} type="button">Cancel</button>
          <button className="button primary" disabled={saving} type="submit">{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </div>
  );
}

function FormFields({ data, tab, values, setValue }: { data: UniverseData; tab: Tab; values: FormValues; setValue: (name: string, value: FormValue) => void }) {
  if (tab === "competitors") return <CompetitorFields values={values} setValue={setValue} />;
  if (tab === "products") return <ProductFields values={values} setValue={setValue} owned />;
  if (tab === "competitor-products") return <>
    <Select label="Competitor" name="competitor_id" required value={String(values.competitor_id ?? "")} onChange={setValue} options={data.competitors.filter((item) => !item.archived_at).map((item) => [item.id, item.name])} />
    <ProductFields values={values} setValue={setValue} owned={false} />
  </>;
  return <BattleCardFields data={data} values={values} setValue={setValue} />;
}

function BattleCardFields({ data, values, setValue }: { data: UniverseData; values: FormValues; setValue: (name: string, value: FormValue) => void }) {
  const selected = Array.isArray(values.competitor_product_ids) ? values.competitor_product_ids : [];
  const basis = isBasisMap(values.item_basis) ? values.item_basis : {};

  function updateBasis(id: string, field: keyof BattleCardBasis, value: string | boolean | number | null) {
    const current = basis[id] ?? {
      priority_order: selected.indexOf(id), same_pack_basis: false, same_price_band: false,
      same_category: false, same_use_case: false, notes: null,
    };
    setValue("item_basis", { ...basis, [id]: { ...current, [field]: value } });
  }

  return <>
    <Input label="Battle-card name" name="name" required value={String(values.name ?? "")} onChange={setValue} />
    <Select label="Owned product" name="product_id" required value={String(values.product_id ?? "")} onChange={setValue} options={data.products.filter((item) => !item.archived_at).map((item) => [item.id, `${item.name} · ${item.internal_sku}`])} />
    <Select label="Status" name="status" required value={String(values.status ?? "draft")} onChange={setValue} options={[["draft", "Draft"], ["approved", "Approved"]]} />
    <Input label="Comparison notes" name="comparison_notes" value={String(values.comparison_notes ?? "")} onChange={setValue} wide />
    <fieldset className="mapping-fieldset"><legend>Direct competitor products</legend>
      {data.competitorProducts.filter((item) => !item.archived_at).length ? data.competitorProducts.filter((item) => !item.archived_at).map((item) => {
        const checked = selected.includes(item.id);
        const itemBasis = basis[item.id];
        return <div className={checked ? "mapping-card selected" : "mapping-card"} key={item.id}>
          <label className="mapping-option">
            <input checked={checked} onChange={(event) => setValue("competitor_product_ids", event.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))} type="checkbox" />
            <span><strong>{item.name}</strong><small>{item.marketplace_product_id ?? "No ASIN"}</small></span>
          </label>
          {checked ? <div className="basis-editor">
            <label>Priority<input min="0" onChange={(event) => updateBasis(item.id, "priority_order", event.target.value === "" ? null : Number(event.target.value))} type="number" value={itemBasis?.priority_order ?? selected.indexOf(item.id)} /></label>
            <label><input checked={itemBasis?.same_pack_basis ?? false} onChange={(event) => updateBasis(item.id, "same_pack_basis", event.target.checked)} type="checkbox" />Same pack</label>
            <label><input checked={itemBasis?.same_price_band ?? false} onChange={(event) => updateBasis(item.id, "same_price_band", event.target.checked)} type="checkbox" />Price band</label>
            <label><input checked={itemBasis?.same_category ?? false} onChange={(event) => updateBasis(item.id, "same_category", event.target.checked)} type="checkbox" />Category</label>
            <label><input checked={itemBasis?.same_use_case ?? false} onChange={(event) => updateBasis(item.id, "same_use_case", event.target.checked)} type="checkbox" />Use case</label>
            <label className="basis-notes">Item notes<input onChange={(event) => updateBasis(item.id, "notes", event.target.value || null)} value={itemBasis?.notes ?? ""} /></label>
          </div> : null}
        </div>;
      }) : <span className="field-hint">Create an active competitor product before adding battle-card items.</span>}
    </fieldset>
  </>;
}

function CompetitorFields({ values, setValue }: { values: FormValues; setValue: (name: string, value: string) => void }) {
  return <>
    <Input label="Competitor name" name="name" required value={String(values.name ?? "")} onChange={setValue} />
    <Input label="Parent company" name="parent_company" value={String(values.parent_company ?? "")} onChange={setValue} />
    <Input label="Amazon store URL" name="amazon_store_url" type="url" value={String(values.amazon_store_url ?? "")} onChange={setValue} wide />
    <Input label="Amazon seller ID" name="amazon_seller_id" value={String(values.amazon_seller_id ?? "")} onChange={setValue} />
    <Input label="Category presence" name="category_presence" value={String(values.category_presence ?? "")} onChange={setValue} />
    <Select label="Positioning" name="positioning_tier" value={String(values.positioning_tier ?? "unknown")} onChange={setValue} options={[["unknown", "Unknown"], ["premium", "Premium"], ["mid", "Mid"], ["value", "Value"]]} />
    <Input label="Threat rating (1–5)" max="5" min="1" name="threat_rating" type="number" value={String(values.threat_rating ?? "")} onChange={setValue} />
    <Input label="Analyst owner" name="analyst_owner" value={String(values.analyst_owner ?? "")} onChange={setValue} />
    <Input label="Notes" name="notes" value={String(values.notes ?? "")} onChange={setValue} wide />
  </>;
}

function ProductFields({ values, setValue, owned }: { values: FormValues; setValue: (name: string, value: string) => void; owned: boolean }) {
  return <>
    {owned ? <Input label="Internal SKU" name="internal_sku" required value={String(values.internal_sku ?? "")} onChange={setValue} /> : null}
    <Input label="Product name" name="name" required value={String(values.name ?? "")} onChange={setValue} />
    <Input label="Brand" name="brand" required value={String(values.brand ?? "")} onChange={setValue} />
    <Input label="Category" name="category" required value={String(values.category ?? "")} onChange={setValue} />
    <Input label="Amazon ASIN" maxLength={10} name="marketplace_product_id" value={String(values.marketplace_product_id ?? "")} onChange={(name, value) => setValue(name, value.toUpperCase())} />
    <Input label="Amazon product URL" name="product_url" type="url" value={String(values.product_url ?? "")} onChange={setValue} wide />
    <Input label="Pack quantity" min="1" name="pack_quantity" type="number" value={String(values.pack_quantity ?? "")} onChange={setValue} />
    <Input label="Pack unit" name="pack_unit" value={String(values.pack_unit ?? "")} onChange={setValue} />
    <Select label="Tracking tier" name="tracking_tier" required value={String(values.tracking_tier ?? "T1")} onChange={setValue} options={[["T1", "T1 · Hourly"], ["T2", "T2 · Every 4 hours"], ["T3", "T3 · Daily"]]} />
  </>;
}

function Input({ label, name, value, onChange, wide = false, ...props }: { label: string; name: string; value: string; onChange: (name: string, value: string) => void; wide?: boolean } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "name" | "value" | "onChange">) {
  return <label className={wide ? "field wide" : "field"}><span>{label}</span><input name={name} value={value} onChange={(event) => onChange(name, event.target.value)} {...props} /></label>;
}

function Select({ label, name, value, options, onChange, required = false }: { label: string; name: string; value: string; options: string[][]; onChange: (name: string, value: string) => void; required?: boolean }) {
  return <label className="field"><span>{label}</span><select name={name} required={required} value={value} onChange={(event) => onChange(name, event.target.value)}><option value="">Select…</option>{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select></label>;
}

function initialValues(tab: Tab, entity: Entity | null): FormValues {
  if (tab === "competitors") {
    const item = entity as Competitor | null;
    return { name: item?.name ?? "", parent_company: item?.parent_company ?? "", amazon_store_url: item?.amazon_store_url ?? "", amazon_seller_id: item?.amazon_seller_id ?? "", category_presence: item?.category_presence ?? "", positioning_tier: item?.positioning_tier ?? "unknown", threat_rating: item?.threat_rating?.toString() ?? "", analyst_owner: item?.analyst_owner ?? "", notes: item?.notes ?? "" };
  }
  if (tab === "products" || tab === "competitor-products") {
    const item = entity as Product | CompetitorProduct | null;
    return { competitor_id: item && "competitor_id" in item ? item.competitor_id : "", internal_sku: item && "internal_sku" in item ? item.internal_sku : "", name: item?.name ?? "", brand: item?.brand ?? "", category: item?.category ?? "", marketplace_product_id: item?.marketplace_product_id ?? "", product_url: item?.product_url ?? "", pack_quantity: item?.pack_quantity?.toString() ?? "", pack_unit: item?.pack_unit ?? "", tracking_tier: item?.tracking_tier ?? "T1" };
  }
  const item = entity as BattleCard | null;
  const items = item?.items ?? [];
  return {
    name: item?.name ?? "",
    product_id: item?.product_id ?? "",
    status: item?.status ?? "draft",
    comparison_notes: item?.comparison_notes ?? "",
    competitor_product_ids: items.filter((entry) => !entry.archived_at).map((entry) => entry.competitor_product_id),
    item_basis: Object.fromEntries(
      items.map((entry) => [entry.competitor_product_id, {
        priority_order: entry.priority_order,
        same_pack_basis: entry.same_pack_basis,
        same_price_band: entry.same_price_band,
        same_category: entry.same_category,
        same_use_case: entry.same_use_case,
        notes: entry.notes,
      }]),
    ),
  };
}

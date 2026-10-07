import { useState } from "react";
import { requestHouseDesignOptions, selectHouseDesignOption } from "./api";

type Props = { projectId: string | null; onProjectId: (id: string) => void; onGenerated: (data: Record<string, any>) => void };

export function HouseDesignStudio({ projectId, onProjectId, onGenerated }: Props) {
  const [plotWidth, setPlotWidth] = useState("");
  const [plotLength, setPlotLength] = useState("");
  const [plotArea, setPlotArea] = useState("");
  const [floors, setFloors] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [bathrooms, setBathrooms] = useState("");
  const [location, setLocation] = useState("");
  const [style, setStyle] = useState("modern");
  const [interior, setInterior] = useState("modern_minimal");
  const [palette, setPalette] = useState("contemporary");
  const [highRainfall, setHighRainfall] = useState(false);
  const [parking, setParking] = useState(false);
  const [balcony, setBalcony] = useState(false);
  const [options, setOptions] = useState<Record<string, any>[]>([]);
  const [questions, setQuestions] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function plan() {
    setBusy(true); setError(null);
    try {
      const requirements: Record<string, unknown> = { project_id: projectId, plot_unit: "ft", style, interior_style: interior, color_palette: palette, location: location || null, parking, balcony, climate: highRainfall ? { rainfall_class: "high" } : {} };
      if (plotWidth) requirements.plot_width = Number(plotWidth);
      if (plotLength) requirements.plot_length = Number(plotLength);
      if (plotArea) requirements.plot_area_sqft = Number(plotArea);
      if (floors) requirements.floors = Number(floors);
      if (bedrooms) requirements.bedrooms = Number(bedrooms);
      if (bathrooms) requirements.bathrooms = Number(bathrooms);
      const result = await requestHouseDesignOptions(requirements);
      onProjectId(result.project_id);
      setOptions(result.options ?? []); setQuestions(result.questions ?? []);
      setAnalysis(result);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function choose(optionId: string) {
    if (!projectId) return;
    setBusy(true); setError(null);
    try { onGenerated(await selectHouseDesignOption(projectId, optionId)); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  if (!expanded) return <button type="button" className="house-studio-launch" onClick={() => setExpanded(true)}>⌂ House Design Studio · Plan requirements and compare options</button>;
  return <section className="house-design-studio" aria-label="House Design Studio">
    <header><div><h3>House Design Studio</h3><p>Set requirements, compare distinct plans, then select one to generate.</p></div><button type="button" onClick={() => setExpanded(false)} aria-label="Close house design studio">×</button></header>
    <div className="house-requirements-grid">
      <label>Plot width (ft)<input value={plotWidth} onChange={(e) => setPlotWidth(e.target.value)} inputMode="decimal" /></label>
      <label>Plot length (ft)<input value={plotLength} onChange={(e) => setPlotLength(e.target.value)} inputMode="decimal" /></label>
      <label>Plot area (sq ft)<input value={plotArea} onChange={(e) => setPlotArea(e.target.value)} inputMode="decimal" /></label>
      <label>Floors<input value={floors} onChange={(e) => setFloors(e.target.value)} inputMode="numeric" /></label>
      <label>Bedrooms<input value={bedrooms} onChange={(e) => setBedrooms(e.target.value)} inputMode="numeric" /></label>
      <label>Bathrooms<input value={bathrooms} onChange={(e) => setBathrooms(e.target.value)} inputMode="numeric" /></label>
      <label>Location<input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Optional" /></label>
      <label>Architecture<select value={style} onChange={(e) => setStyle(e.target.value)}><option>modern</option><option>traditional</option><option>contemporary</option><option>tropical</option><option>luxury</option></select></label>
      <label>Interior<select value={interior} onChange={(e) => setInterior(e.target.value)}><option value="modern_minimal">Modern Minimal</option><option value="modern_luxury">Modern Luxury</option><option value="indian_contemporary">Indian Contemporary</option><option value="premium">Premium</option><option value="budget_efficient">Budget Efficient</option></select></label>
      <label>Palette<select value={palette} onChange={(e) => setPalette(e.target.value)}><option value="contemporary">Contemporary</option><option value="modern_vibrant">Modern Vibrant</option><option value="warm_luxury">Warm Luxury</option><option value="tropical">Tropical</option></select></label>
    </div>
    <div className="house-requirement-toggles"><label><input type="checkbox" checked={parking} onChange={(e) => setParking(e.target.checked)} /> Parking</label><label><input type="checkbox" checked={balcony} onChange={(e) => setBalcony(e.target.checked)} /> Balcony</label><label><input type="checkbox" checked={highRainfall} onChange={(e) => setHighRainfall(e.target.checked)} /> User specified high rainfall</label></div>
    <button type="button" className="house-plan-button" onClick={() => void plan()} disabled={busy}>{busy ? "Planning…" : "Generate design options"}</button>
    {questions.length > 0 && <div className="house-clarifications" role="status">{questions.map((q) => <p key={q}>{q}</p>)}</div>}
    {analysis?.site_analysis && <div className="house-site-summary"><strong>Site analysis · concept estimate</strong><span>Plot area: {analysis.site_analysis.plot_area_sqft ?? "Not specified"} sq ft</span><span>Footprint estimate: {analysis.site_analysis.estimated_footprint_sqft ?? "Not available"} sq ft</span><span>Setbacks: {analysis.site_analysis.setbacks}</span>{analysis.site_analysis.assumptions?.map((a: string) => <small key={a}>{a}</small>)}</div>}
    {options.length > 0 && <div className="house-option-grid">{options.map((option) => <article key={option.option_id} className="house-option-card"><h4>{option.name}</h4><div className="house-option-swatches">{Object.values(option.palette_values as Record<string, string>).map((color, i) => <i key={i} style={{ background: color }} />)}</div><p>Roof: {option.roof_type} · slope {option.roof_slope_deg}°</p><p>Overhang: {option.overhang_mm} mm · Ventilation: {option.ventilation}</p><p>{option.interior_style.replaceAll("_", " ")} · {option.palette.replaceAll("_", " ")}</p><button type="button" onClick={() => void choose(option.option_id)} disabled={busy}>Select and generate</button></article>)}</div>}
    {analysis?.room_allocation?.floors?.map((floor: Record<string, any>) => <p key={floor.floor}>Floor {floor.floor}: {floor.rooms?.map((room: Record<string, any>) => `${room.type} ${room.area_sqft} sq ft`).join(" · ")}</p>)}
    {error && <p role="alert" className="house-error">{error}</p>}
  </section>;
}

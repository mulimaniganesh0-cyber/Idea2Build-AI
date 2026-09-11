import { FormEvent, useState } from "react";
import { parseDesign } from "./api";
import { ModelViewport } from "./ModelViewport";
import type { DesignSpec } from "./types";

const INITIAL_PROMPT = "Create a box 5m x 3m x 2m";

export default function App() {
  const [prompt, setPrompt] = useState(INITIAL_PROMPT);
  const [design, setDesign] = useState<DesignSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      setDesign(await parseDesign(prompt));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unexpected error");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">PHASE 1 · PROMPT TO GEOMETRY</p>
          <h1>AI-CAD Engineer</h1>
        </div>
        <span className="badge">Prototype · Not for engineering approval</span>
      </header>

      <section className="workspace">
        <aside className="panel controls">
          <h2>Create a primitive</h2>
          <p>Phase 1 currently supports a box with three dimensions and a unit.</p>
          <form onSubmit={handleSubmit}>
            <label htmlFor="prompt">Design request</label>
            <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} />
            <button disabled={isLoading} type="submit">{isLoading ? "Generating…" : "Generate model"}</button>
          </form>
          {error && <p className="error" role="alert">{error}</p>}
          <p className="hint">Try: “Create a box 500mm x 300mm x 200mm”</p>
        </aside>

        <section className="canvas-panel">
          <ModelViewport design={design} />
          {!design && <p className="empty-state">Generate a box to inspect it here.</p>}
        </section>

        <aside className="panel inspector">
          <h2>Design specification</h2>
          {design ? (
            <>
              <dl>
                <div><dt>Object</dt><dd>{design.object_type}</dd></div>
                <div><dt>Length</dt><dd>{design.dimensions.length} {design.unit}</dd></div>
                <div><dt>Width</dt><dd>{design.dimensions.width} {design.unit}</dd></div>
                <div><dt>Height</dt><dd>{design.dimensions.height} {design.unit}</dd></div>
              </dl>
              <h3>Canonical dimensions</h3>
              <p>{design.dimensions_mm.length} × {design.dimensions_mm.width} × {design.dimensions_mm.height} mm</p>
              {design.warnings.map((warning) => <p className="warning" key={warning}>{warning}</p>)}
            </>
          ) : <p>No generated design yet.</p>}
        </aside>
      </section>
    </main>
  );
}


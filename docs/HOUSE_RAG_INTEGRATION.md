# House RAG-to-design integration

## Behavior

House option generation only requests RAG when the caller enables it and supplies explicit climate inputs (`rainfall_class`, `temperature_class`, or `humidity_pct`). A location label by itself does not cause invented climate values or a fabricated weather lookup.

`create_design_options` passes the structured climate profile to the existing pgvector `retrieve` service. When the explicit profile says high rainfall and retrieved text actually contains roof/rain/drain/gutter guidance, the Climate Optimized option adds gutter guidance and the decision record cites returned chunk IDs. The selected option carries this parameter into house state, the parametric design, the viewer components, and the canonical component tree.

If retrieval fails or returns no relevant context, generation can continue. The knowledge status, trace, and returned source chunks are stored in project house state. The inspector does not show RAG as used unless retrieval actually returned sources.

## A/B regression

`test_rag_ab_decision_and_provenance_marker_reach_design_planner` supplies a controlled marker result from the retrieval boundary and compares identical high-rainfall requirements with retrieval enabled and disabled. It asserts the source marker reaches the planner, the gutter parameter changes, the option hash changes, and the source chunk ID is recorded.

This is an integration-boundary test, not a live pgvector corpus experiment. It does not prove that the currently indexed production corpus contains a relevant house-climate source or that external climate observations are available. Run a live A/B after adding a vetted house-climate document to the configured index.

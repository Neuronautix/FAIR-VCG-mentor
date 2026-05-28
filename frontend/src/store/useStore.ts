import { create } from 'zustand'

export interface ColumnProfile {
  name: string
  label: string
  description: string | null
  inferred_type: string
  data_type: string
  unique_values: number
  missing_values: number
  missing_pct: number
  sample_values: string[]
  unit_guess: string | null
  confidence: number
  reason_codes?: string[]
  user_label: string | null
  user_description: string | null
  user_unit: string | null
  user_type: string | null
  allowed_values: string[] | null
  required: boolean
  uri: string | null
}

export interface LowConfidenceColumn {
  name: string
  inferred_type: string
  confidence: number
  sample_values: string[]
  reason_codes: string[]
}

export interface InferenceMetrics {
  total_updates: number
  type_corrections: number
  label_corrections: number
  unit_corrections: number
}

export interface ImportInfo {
  filename: string
  n_rows: number
  n_columns: number
  delimiter: string
  encoding: string
  has_header: boolean
  empty_columns: string[]
  duplicate_columns: string[]
  malformed_rows: number[]
  signature?: string
}

export interface TableStructure {
  table_shape: string
  row_represents: string
  primary_entity: string
  secondary_entity: string | null
  detected_identifiers: string[]
  detected_measurements: string[]
  detected_categoricals: string[]
  detected_time_vars: string[]
}

export interface Issue {
  id: string
  severity: 'high' | 'medium' | 'low'
  category: string
  column: string | null
  problem: string
  why_it_matters: string
  suggested_fix: string
}

export interface FAIRDimension {
  score: number
  max_score: number
  main_weakness: string
  criteria: Record<string, boolean>
}

export interface FAIRScore {
  fair_score: number
  findable: FAIRDimension
  accessible: FAIRDimension
  interoperable: FAIRDimension
  reusable: FAIRDimension
  main_recommendations: string[]
}

export interface DatasetMetadata {
  title?: string
  description?: string
  creator?: string
  institution?: string
  contact_email?: string
  date_created?: string
  version?: string
  license?: string
  access_conditions?: string
  species?: string
  study_type?: string
  protocol_reference?: string
  funding_source?: string
  keywords?: string[]
  row_represents?: string
  primary_identifier?: string
  base_uri?: string
}

export interface ARRIVEField {
  value: string | null
  status: 'found' | 'inferred' | 'missing'
}

export interface PaperExtraction {
  _filename: string
  _file_size_kb: number
  _method: string
  dataset_metadata: {
    title: string | null
    description: string | null
    creator: string | null
    institution: string | null
    species: string | null
    study_type: string | null
    keywords: string[]
    license: string | null
    funding_source: string | null
    protocol_reference: string | null
  }
  arrive: Record<string, ARRIVEField>
  summary: string
  // vcg_hints kept for backward compatibility with paper_extractor responses
  vcg_hints?: Record<string, any>
}

export interface TemplateSummary {
  id: string
  name: string
  version: string
  description?: string
  source: 'builtin' | 'user'
  conforms_to: string[]
}

export interface TemplateCandidate {
  id: string
  name: string
  score: number
  reasons: string[]
}

export interface ChatMessage {
  role: 'user' | 'agent'
  content: string
  options?: string[]
}

export interface ConformanceEntry {
  standard: string
  section: string
  arrive_section?: string
  prepare_section?: string
  field_id: string
  status: 'satisfied' | 'missing' | 'partial'
  satisfied_by: { column?: string; metadata?: string; via_crosswalk?: boolean } | null
  severity: 'high' | 'medium' | 'low'
  is_column_field: boolean
}

interface AppState {
  datasetId: string | null
  importInfo: ImportInfo | null
  columns: ColumnProfile[]
  tableStructure: TableStructure | null
  issues: Issue[]
  fairScore: FAIRScore | null
  metadata: DatasetMetadata
  lowConfidenceColumns: LowConfidenceColumn[]
  templateApplied: number
  inferenceMetrics: InferenceMetrics

  paperExtraction: PaperExtraction | null

  aiConfigured: boolean | null
  hitlSuggestions: import('../api/client').HITLSuggestion[]
  vocabulary: import('../api/client').Vocabulary | null

  templateId: string | null
  templateCandidates: TemplateCandidate[]
  templateConformance: ConformanceEntry[]
  availableTemplates: { builtin: TemplateSummary[]; user: TemplateSummary[] }
  templateCompletion: import('../api/client').TemplateCompletionReport | null

  setUploadResult: (
    datasetId: string,
    importInfo: ImportInfo,
    columns: ColumnProfile[],
    tableStructure: TableStructure,
    issues: Issue[],
    extras?: {
      lowConfidenceColumns?: LowConfidenceColumn[]
      templateApplied?: number
      templateId?: string | null
      templateCandidates?: TemplateCandidate[]
    }
  ) => void
  setColumns: (columns: ColumnProfile[]) => void
  setIssues: (issues: Issue[]) => void
  setFairScore: (score: FAIRScore | null) => void
  setMetadata: (metadata: DatasetMetadata) => void
  setLowConfidenceColumns: (cols: LowConfidenceColumn[]) => void
  setInferenceMetrics: (metrics: InferenceMetrics) => void
  reset: () => void

  setPaperExtraction: (extraction: PaperExtraction | null) => void

  setAIConfigured: (configured: boolean | null) => void
  setHITLSuggestions: (suggestions: import('../api/client').HITLSuggestion[]) => void
  setVocabulary: (vocab: import('../api/client').Vocabulary | null) => void

  setTemplateId: (id: string | null) => void
  setTemplateCandidates: (c: TemplateCandidate[]) => void
  setTemplateConformance: (r: ConformanceEntry[]) => void
  setAvailableTemplates: (t: { builtin: TemplateSummary[]; user: TemplateSummary[] }) => void
  setTemplateCompletion: (r: import('../api/client').TemplateCompletionReport | null) => void
}

const EMPTY_METRICS: InferenceMetrics = {
  total_updates: 0,
  type_corrections: 0,
  label_corrections: 0,
  unit_corrections: 0,
}

export const useStore = create<AppState>((set) => ({
  datasetId: null,
  importInfo: null,
  columns: [],
  tableStructure: null,
  issues: [],
  fairScore: null,
  metadata: { base_uri: 'https://your-lab.org' },
  lowConfidenceColumns: [],
  templateApplied: 0,
  inferenceMetrics: EMPTY_METRICS,

  paperExtraction: null,

  aiConfigured: null,
  hitlSuggestions: [],
  vocabulary: null,

  templateId: null,
  templateCandidates: [],
  templateConformance: [],
  availableTemplates: { builtin: [], user: [] },
  templateCompletion: null,

  setUploadResult: (datasetId, importInfo, columns, tableStructure, issues, extras) =>
    set({
      datasetId,
      importInfo,
      columns,
      tableStructure,
      issues,
      fairScore: null,
      lowConfidenceColumns: extras?.lowConfidenceColumns ?? [],
      templateApplied: extras?.templateApplied ?? 0,
      inferenceMetrics: EMPTY_METRICS,
      templateId: extras?.templateId ?? null,
      templateCandidates: extras?.templateCandidates ?? [],
      templateConformance: [],
    }),

  setColumns: (columns) => set({ columns }),
  setIssues: (issues) => set({ issues }),
  setFairScore: (fairScore) => set({ fairScore }),
  setMetadata: (metadata) => set((s) => ({ metadata: { ...s.metadata, ...metadata } })),
  setLowConfidenceColumns: (cols) => set({ lowConfidenceColumns: cols }),
  setInferenceMetrics: (metrics) => set({ inferenceMetrics: metrics }),

  reset: () =>
    set({
      datasetId: null,
      importInfo: null,
      columns: [],
      tableStructure: null,
      issues: [],
      fairScore: null,
      metadata: { base_uri: 'https://your-lab.org' },
      lowConfidenceColumns: [],
      templateApplied: 0,
      inferenceMetrics: EMPTY_METRICS,
      paperExtraction: null,
      hitlSuggestions: [],
      vocabulary: null,
      templateId: null,
      templateCandidates: [],
      templateConformance: [],
      templateCompletion: null,
    }),

  setPaperExtraction: (extraction) => set({ paperExtraction: extraction }),

  setAIConfigured: (aiConfigured) => set({ aiConfigured }),
  setHITLSuggestions: (hitlSuggestions) => set({ hitlSuggestions }),
  setVocabulary: (vocabulary) => set({ vocabulary }),

  setTemplateId: (templateId) => set({ templateId }),
  setTemplateCandidates: (templateCandidates) => set({ templateCandidates }),
  setTemplateConformance: (templateConformance) => set({ templateConformance }),
  setAvailableTemplates: (availableTemplates) => set({ availableTemplates }),
  setTemplateCompletion: (templateCompletion) => set({ templateCompletion }),
}))

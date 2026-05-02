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
  user_label: string | null
  user_description: string | null
  user_unit: string | null
  user_type: string | null
  allowed_values: string[] | null
  required: boolean
  uri: string | null
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

export interface VCGColumnRoles {
  subject_id: string | null
  treatment_col: string | null
  treatment_value: string | null
  control_value: string | null
  outcome_cols: string[]
  covariate_cols: string[]
  time_col: string | null
  exclude_cols: string[]
}

export interface VCGConfig {
  method: string          // "bootstrap"|"synthetic"|"auto"
  n_synthetic: number
  seed: number
  bootstrap_iters: number
  confidence_level: number
}

export interface ChatMessage {
  role: 'agent' | 'user'
  content: string
  state?: string
  options?: string[]
  ready_to_build?: boolean
  timestamp: string
}

export interface VCGResults {
  method_used: string
  n_subjects_real: number
  n_subjects_vcg: number
  balance_report: {
    covariates: Array<{col: string, smd: number, balance_label: string}>
    outcomes: Array<{col: string, mean_real: number, sd_real: number, mean_vcg: number, sd_vcg: number, p_value: number}>
  }
  diagnostic_plots: Record<string, string>   // base64 PNG strings
  stat_report: string
  generated_at: string
}

interface AppState {
  datasetId: string | null
  importInfo: ImportInfo | null
  columns: ColumnProfile[]
  tableStructure: TableStructure | null
  issues: Issue[]
  fairScore: FAIRScore | null
  metadata: DatasetMetadata

  vcgStatus: 'not_started' | 'running' | 'done' | 'failed' | null
  vcgResults: VCGResults | null
  vcgConversation: ChatMessage[]
  vcgColumnRoles: VCGColumnRoles | null
  vcgConfig: VCGConfig | null

  setUploadResult: (
    datasetId: string,
    importInfo: ImportInfo,
    columns: ColumnProfile[],
    tableStructure: TableStructure,
    issues: Issue[]
  ) => void
  setColumns: (columns: ColumnProfile[]) => void
  setIssues: (issues: Issue[]) => void
  setFairScore: (score: FAIRScore | null) => void
  setMetadata: (metadata: DatasetMetadata) => void
  reset: () => void

  setVCGStatus: (status: AppState['vcgStatus']) => void
  setVCGResults: (results: VCGResults | null) => void
  addChatMessage: (msg: ChatMessage) => void
  clearVCGConversation: () => void
  setVCGColumnRoles: (roles: VCGColumnRoles) => void
  setVCGConfig: (config: VCGConfig) => void
}

export const useStore = create<AppState>((set) => ({
  datasetId: null,
  importInfo: null,
  columns: [],
  tableStructure: null,
  issues: [],
  fairScore: null,
  metadata: { base_uri: 'https://your-lab.org' },

  vcgStatus: null,
  vcgResults: null,
  vcgConversation: [],
  vcgColumnRoles: null,
  vcgConfig: null,

  setUploadResult: (datasetId, importInfo, columns, tableStructure, issues) =>
    set({ datasetId, importInfo, columns, tableStructure, issues, fairScore: null }),

  setColumns: (columns) => set({ columns }),
  setIssues: (issues) => set({ issues }),
  setFairScore: (fairScore) => set({ fairScore }),
  setMetadata: (metadata) => set((s) => ({ metadata: { ...s.metadata, ...metadata } })),

  reset: () =>
    set({
      datasetId: null,
      importInfo: null,
      columns: [],
      tableStructure: null,
      issues: [],
      fairScore: null,
      metadata: { base_uri: 'https://your-lab.org' },
      vcgStatus: null,
      vcgResults: null,
      vcgConversation: [],
      vcgColumnRoles: null,
      vcgConfig: null,
    }),

  setVCGStatus: (status) => set({ vcgStatus: status }),
  setVCGResults: (results) => set({ vcgResults: results }),
  addChatMessage: (msg) => set((s) => ({ vcgConversation: [...s.vcgConversation, msg] })),
  clearVCGConversation: () => set({ vcgConversation: [] }),
  setVCGColumnRoles: (roles) => set({ vcgColumnRoles: roles }),
  setVCGConfig: (config) => set({ vcgConfig: config }),
}))

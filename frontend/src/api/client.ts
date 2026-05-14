import axios from 'axios'
import type {
  ColumnProfile,
  DatasetMetadata,
  FAIRScore,
  ImportInfo,
  InferenceMetrics,
  Issue,
  LowConfidenceColumn,
  TableStructure,
} from '../store/useStore'

const api = axios.create({ baseURL: '/api' })

export interface UploadResponse {
  dataset_id: string
  import_info: ImportInfo
  columns: ColumnProfile[]
  table_structure: TableStructure
  issues: Issue[]
  template_applied?: number
  low_confidence_columns?: LowConfidenceColumn[]
}

export const uploadCSV = (file: File): Promise<UploadResponse> => {
  const form = new FormData()
  form.append('file', file)
  return api.post<UploadResponse>('/upload', form).then((r) => r.data)
}

export const getProfile = (id: string) =>
  api.get<{ import_info: ImportInfo; columns: ColumnProfile[]; table_structure: TableStructure }>(`/profile/${id}`).then((r) => r.data)

export const getIssues = (id: string) =>
  api.get<{ issues: Issue[] }>(`/issues/${id}`).then((r) => r.data)

export interface UpdateColumnsResponse {
  columns: ColumnProfile[]
  issues: Issue[]
  low_confidence_columns?: LowConfidenceColumn[]
  inference_metrics?: InferenceMetrics
}

export const updateColumns = (id: string, columns: ColumnProfile[]) =>
  api.put<UpdateColumnsResponse>(`/columns/${id}`, columns).then((r) => r.data)

export interface TemplateInfo {
  signature: string | null
  exists: boolean
  applied: number
  source_filename: string | null
  updated_at: number | null
  low_confidence_columns: LowConfidenceColumn[]
  inference_metrics: InferenceMetrics
}

export const getTemplateInfo = (id: string) =>
  api.get<TemplateInfo>(`/templates/${id}`).then((r) => r.data)

export const saveTemplate = (id: string) =>
  api.post<{ signature: string; n_columns: number }>(`/templates/${id}`).then((r) => r.data)

export const getMetadata = (id: string) =>
  api.get<{ metadata: DatasetMetadata }>(`/metadata/${id}`).then((r) => r.data)

export const saveMetadata = (id: string, metadata: DatasetMetadata) =>
  api.put<{ metadata: DatasetMetadata }>(`/metadata/${id}`, metadata).then((r) => r.data)

export const getFairScore = (id: string): Promise<FAIRScore> =>
  api.get<FAIRScore>(`/fair-score/${id}`).then((r) => r.data)

export const getLLMFairScore = (id: string) =>
  api.get(`/fair-score/${id}/llm`).then((r) => r.data)

export const getUriSuggestions = (id: string) =>
  api.get(`/uris/${id}`).then((r) => r.data)

export const exportUrl = (id: string, type: string) => `/api/export/${id}/${type}`

export const arriveExportUrl = (id: string) => `/api/export/${id}/arrive`

export const getVCGWizardPrefill = (id: string) =>
  api.get(`/vcg/${id}/wizard-prefill`).then(r => r.data)

export const saveVCGWizard = (id: string, payload: object) =>
  api.put(`/vcg/${id}/wizard`, payload).then(r => r.data)

export const startVCGChat = (id: string) =>
  api.post(`/vcg/${id}/chat/start`).then(r => r.data)

export const respondVCGChat = (id: string, message: string) =>
  api.post(`/vcg/${id}/chat/respond`, { message }).then(r => r.data)

export const startVCGGeneration = (id: string) =>
  api.post(`/vcg/${id}/generate`).then(r => r.data)

export const getVCGSuitability = (id: string) =>
  api.get(`/vcg/${id}/suitability`).then(r => r.data)

export const getVCGStatus = (id: string) =>
  api.get(`/vcg/${id}/status`).then(r => r.data)

export const getVCGResults = (id: string) =>
  api.get(`/vcg/${id}/results`).then(r => r.data)

export const getVCGConversation = (id: string) =>
  api.get(`/vcg/${id}/conversation`).then(r => r.data)

export const vcgExportUrl = (id: string, type: 'vcg-csv' | 'vcg-report') =>
  `/api/vcg/${id}/export/${type}`

export const extractPaperMetadata = (file: File): Promise<any> => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/paper/extract', form).then((r) => r.data)
}

export const extractPaperMetadataStream = (
  file: File,
  onStatus: (msg: string) => void,
  onResult: (data: any) => void,
  onError: (msg: string) => void,
): Promise<void> => {
  const form = new FormData()
  form.append('file', file)
  return fetch('/api/paper/extract/stream', { method: 'POST', body: form }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text)
    }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'status') onStatus(event.message)
            else if (event.type === 'result') onResult(event.data)
            else if (event.type === 'error') onError(event.message)
          } catch {}
        }
      }
    }
  })
}

export const fetchPaperByDOI = (doi: string): Promise<any> =>
  api.post('/paper/doi', { doi }).then((r) => r.data)

export const storePaperExtraction = (id: string, extraction: any): Promise<void> =>
  api.put(`/paper/${id}/extraction`, extraction).then(() => undefined)

export const getStoredPaperExtraction = (id: string): Promise<any> =>
  api.get(`/paper/${id}/extraction`).then((r) => r.data)

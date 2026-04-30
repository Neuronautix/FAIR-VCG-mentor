import axios from 'axios'
import type { ColumnProfile, DatasetMetadata, FAIRScore, ImportInfo, Issue, TableStructure } from '../store/useStore'

const api = axios.create({ baseURL: '/api' })

export interface UploadResponse {
  dataset_id: string
  import_info: ImportInfo
  columns: ColumnProfile[]
  table_structure: TableStructure
  issues: Issue[]
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

export const updateColumns = (id: string, columns: ColumnProfile[]) =>
  api.put<{ columns: ColumnProfile[]; issues: Issue[] }>(`/columns/${id}`, columns).then((r) => r.data)

export const getMetadata = (id: string) =>
  api.get<{ metadata: DatasetMetadata }>(`/metadata/${id}`).then((r) => r.data)

export const saveMetadata = (id: string, metadata: DatasetMetadata) =>
  api.put<{ metadata: DatasetMetadata }>(`/metadata/${id}`, metadata).then((r) => r.data)

export const getFairScore = (id: string): Promise<FAIRScore> =>
  api.get<FAIRScore>(`/fair-score/${id}`).then((r) => r.data)

export const getUriSuggestions = (id: string) =>
  api.get(`/uris/${id}`).then((r) => r.data)

export const exportUrl = (id: string, type: string) => `/api/export/${id}/${type}`

export interface Task {
  id: string
  task_type: string
  status: TaskStatus
  stage: TaskStage
  progress: number
  message: string
  details: Record<string, any>
  workspace_id: string
  created_at: number
  started_at: number | null
  completed_at: number | null
  error_message: string | null
  metadata: Record<string, any>
}

export enum TaskStatus {
  PENDING = "pending",
  PROCESSING = "processing", 
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled"
}

export enum TaskStage {
  UPLOADING = "uploading",
  PARSING = "parsing",
  CHUNKING = "chunking", 
  VECTORIZING = "vectorizing",
  INDEXING = "indexing"
}

export interface TaskProgress {
  stage: TaskStage
  progress: number
  message: string
}

export interface TaskQueueStats {
  total_tasks: number
  pending: number
  processing: number
  completed: number
  failed: number
  cancelled: number
  max_workers: number
  running_tasks: number
}
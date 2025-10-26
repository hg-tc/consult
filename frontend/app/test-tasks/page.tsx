"use client"

import { useState, useEffect } from "react"

export default function TaskTestPage() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await fetch('/api/tasks')
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const data = await response.json()
        setTasks(data.tasks || [])
        console.log('Tasks loaded:', data.tasks)
      } catch (err) {
        setError(err.message)
        console.error('Error fetching tasks:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchTasks()
  }, [])

  if (loading) return <div>Loading tasks...</div>
  if (error) return <div>Error: {error}</div>

  const failedTasks = tasks.filter(task => task.status === 'failed')
  const completedTasks = tasks.filter(task => task.status === 'completed')
  const activeTasks = tasks.filter(task => task.status === 'pending' || task.status === 'processing')

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Task Test Page</h1>
      
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Statistics</h2>
        <p>Total tasks: {tasks.length}</p>
        <p>Failed tasks: {failedTasks.length}</p>
        <p>Completed tasks: {completedTasks.length}</p>
        <p>Active tasks: {activeTasks.length}</p>
      </div>

      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-2">Failed Tasks</h2>
        {failedTasks.length > 0 ? (
          <div className="space-y-2">
            {failedTasks.map(task => (
              <div key={task.id} className="p-3 border border-red-200 bg-red-50 rounded">
                <div className="font-medium">{task.metadata?.original_filename || 'Unknown'}</div>
                <div className="text-sm text-red-600">{task.error_message}</div>
                <div className="text-xs text-gray-500">
                  {new Date(task.created_at * 1000).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p>No failed tasks</p>
        )}
      </div>

      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-2">Recent Completed Tasks</h2>
        {completedTasks.slice(0, 5).map(task => (
          <div key={task.id} className="p-3 border border-green-200 bg-green-50 rounded mb-2">
            <div className="font-medium">{task.metadata?.original_filename || 'Unknown'}</div>
            <div className="text-sm text-green-600">{task.message}</div>
            <div className="text-xs text-gray-500">
              {new Date(task.created_at * 1000).toLocaleString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

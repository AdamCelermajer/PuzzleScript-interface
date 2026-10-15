import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import { Layout } from './components/Layout'
import { RunsView } from './views/Runs'
import { LaunchView } from './views/Launch'
import { RunDetailView } from './views/RunDetail'
import { CompareView } from './views/Compare'
import { BenchmarksView } from './views/Benchmarks'
import { DiaryView, DiaryEntryView, DiaryEditView } from './views/Diary'
import { ToolsView } from './views/Tools'
import { Empty } from './components/ui'

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<RunsView />} />
            <Route path="runs" element={<RunsView />} />
            <Route path="runs/*" element={<RunDetailView />} />
            <Route path="launch" element={<LaunchView />} />
            <Route path="compare" element={<CompareView />} />
            <Route path="benchmarks" element={<BenchmarksView />} />
            <Route path="benchmarks/:gameId" element={<BenchmarksView />} />
            <Route path="diary" element={<DiaryView />} />
            <Route path="diary/new" element={<DiaryEditView />} />
            <Route path="diary/:slug" element={<DiaryEntryView />} />
            <Route path="diary/:slug/edit" element={<DiaryEditView />} />
            <Route path="tools" element={<ToolsView />} />
            <Route path="*" element={<Empty title="Page not found">Use the navigation on the left.</Empty>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

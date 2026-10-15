import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import { Layout } from './components/Layout'
import { RunsView } from './views/Runs'
import { ResultsView } from './views/Results'
import { LaunchView } from './views/Launch'
import { RunDetailView } from './views/RunDetail'
import { CompareView } from './views/Compare'
import { BenchmarksView } from './views/Benchmarks'
import { DiaryView, DiaryEntryView, DiaryEditView } from './views/Diary'
import { ToolsView } from './views/Tools'
import { NotesView } from './views/Notes'
// pdf.js + KaTeX are large: load the paper investigation only when it is opened.
const PapersView = lazy(() => import('./views/Papers').then((m) => ({ default: m.PapersView })))
import { OptimalPathView } from './views/OptimalPath'
import { Empty, Loading } from './components/ui'

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<ResultsView />} />
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
            <Route path="tools/notes" element={<NotesView />} />
            <Route path="tools/papers" element={<Suspense fallback={<Loading label="Loading the PDF reader…" />}><PapersView /></Suspense>} />
            <Route path="tools/optimal-path" element={<OptimalPathView />} />
            <Route path="*" element={<Empty title="Page not found">Use the navigation on the left.</Empty>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

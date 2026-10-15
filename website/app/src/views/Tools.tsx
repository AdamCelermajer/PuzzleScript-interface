import { Link } from 'react-router-dom'
import { Card, PageHeader } from '../components/ui'

const TOOLS: { title: string; to: string; description: string }[] = [
  { title: 'Notes', to: '/tools/notes', description: 'Workbench notes, todo and benchmark positioning (docs/notes/*.md).' },
  { title: 'Paper investigation', to: '/tools/papers', description: 'PDF library, underlines, comments and the Codex research copilot.' },
  { title: 'BFS optimal path', to: '/tools/optimal-path', description: 'Breadth-first reference solutions for every level, with replay.' },
]

export function ToolsView() {
  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-4">
      <PageHeader title="Tools" subtitle="Research utilities." />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {TOOLS.map((tool) => (
          <Link key={tool.to} to={tool.to} className="text-fg hover:no-underline">
            <Card title={tool.title} className="h-full hover:border-accent">
              <p className="text-[12.5px] text-muted">{tool.description}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}

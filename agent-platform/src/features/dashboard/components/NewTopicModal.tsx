import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Button, IconButton } from '../../../components/ui'

export function NewTopicModal({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string) => void }) {
  const [name, setName] = useState('')
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><div className="topic-modal" role="dialog" aria-modal="true" aria-labelledby="new-topic-title" onMouseDown={(event) => event.stopPropagation()}><div className="modal-heading"><div><span className="panel-kicker">New workspace</span><h2 id="new-topic-title">Track a market topic</h2></div><IconButton className="icon-button" onClick={onClose} label="Close dialog"><X size={18} /></IconButton></div><label htmlFor="topic-name">Topic name</label><input id="topic-name" autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. AI tools for accountants" /><p>Start with a market name. Research and ideas can be added from chat later.</p><div className="modal-actions"><Button className="secondary-button" variant="secondary" onClick={onClose}>Cancel</Button><Button className="primary-button" disabled={!name.trim()} onClick={() => onCreate(name.trim())}><Plus size={15} />Create topic</Button></div></div></div>
}

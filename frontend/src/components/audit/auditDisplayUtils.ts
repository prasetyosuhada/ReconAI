import { Layers, Sparkles, UserCheck } from 'lucide-react'

export function getActorMeta(actorType?: string) {
  switch (actorType?.toLowerCase()) {
    case 'agent':
      return {
        label: 'AI AGENT',
        badgeClass: 'bg-purple-500/10 border border-purple-500/25 text-purple-300',
        textClass: 'text-purple-400',
        Icon: Sparkles,
      }
    case 'human':
      return {
        label: 'HUMAN',
        badgeClass: 'bg-amber-500/10 border border-amber-500/25 text-amber-300',
        textClass: 'text-amber-400',
        Icon: UserCheck,
      }
    default:
      return {
        label: 'SYSTEM',
        badgeClass: 'bg-slate-800/80 border border-slate-700 text-slate-300',
        textClass: 'text-slate-400',
        Icon: Layers,
      }
  }
}

import { CheckCircle, WarningCircle } from '@phosphor-icons/react'

export default function Toast({ msg, type }) {
  return (
    <div className={`toast ${type}`}>
      {type === 'success'
        ? <CheckCircle size={18} weight="fill" />
        : <WarningCircle size={18} weight="fill" />}
      <span>{msg}</span>
    </div>
  )
}
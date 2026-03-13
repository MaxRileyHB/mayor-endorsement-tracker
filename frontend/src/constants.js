export const STATUSES = [
  { key: 'no_contact_info',    label: 'No Contact Info',     color: 'bg-gray-100 text-gray-600' },
  { key: 'city_contact_only',  label: 'City Contact Only',   color: 'bg-gray-200 text-gray-700' },
  { key: 'info_requested',     label: 'Info Requested',      color: 'bg-amber-100 text-amber-700' },
  { key: 'ready_for_outreach', label: 'Ready for Outreach',  color: 'bg-blue-100 text-blue-700' },
  { key: 'outreach_sent',      label: 'Outreach Sent',       color: 'bg-blue-200 text-blue-800' },
  { key: 'in_conversation',    label: 'In Conversation',     color: 'bg-purple-100 text-purple-700' },
  { key: 'call_scheduled',     label: 'Call Scheduled',      color: 'bg-purple-200 text-purple-800' },
  { key: 'endorsed',           label: 'Endorsed',            color: 'bg-green-100 text-green-700' },
  { key: 'declined',           label: 'Declined',            color: 'bg-red-100 text-red-600' },
  { key: 'follow_up',          label: 'Follow Up',           color: 'bg-amber-200 text-amber-800' },
  { key: 'not_pursuing',       label: 'Not Pursuing',        color: 'bg-gray-100 text-gray-400' },
]

export const STATUS_MAP = Object.fromEntries(STATUSES.map(s => [s.key, s]))

export const TIER_COLORS = {
  1: 'bg-blue-100 text-blue-700 border-blue-200',
  2: 'bg-amber-100 text-amber-700 border-amber-200',
  3: 'bg-gray-100 text-gray-500 border-gray-200',
}

export const CASTES = [
  { id: 'ELITE', label: '精英阶层 (Elite)', color: '#ff4d4f', weight: 0.1, desc: '掌控巨量原始资本，拥有信息溯源权' },
  { id: 'MIDDLE', label: '中产阶层 (Middle)', color: '#1890ff', weight: 0.3, desc: '拥有稳健的起步资金' },
  { id: 'WORKING', label: '工薪阶层 (Working)', color: '#52c41a', weight: 0.6, desc: '白手起家，依赖社交网络获取信息' },
] as const;

export type CasteId = typeof CASTES[number]['id'];

import type { LotId } from './types';

export interface LotDef {
  id: LotId;
  label: string;
  color: string;
  /** visible au chargement */
  visible: boolean;
}

export const LOTS: LotDef[] = [
  { id: 'archi', label: 'Architecture', color: '#B8B2A7', visible: true },
  { id: 'chauffage', label: 'Chauffage', color: '#E4572E', visible: true },
  { id: 'ecs', label: 'ECS', color: '#C2185B', visible: true },
  { id: 'ef', label: 'Eau froide', color: '#1E88E5', visible: true },
  { id: 'ventilation', label: 'Ventilation', color: '#2E9E5B', visible: true },
  { id: 'equipements', label: 'Équipements', color: '#7E57C2', visible: true },
  { id: 'electrique', label: 'Électrique', color: '#F2B705', visible: true },
  { id: 'autres', label: 'Autres', color: '#8D99A6', visible: true },
  { id: 'espaces', label: 'Pièces (volumes)', color: '#5FB49C', visible: false },
];

export const LOT_BY_ID: Record<LotId, LotDef> = Object.fromEntries(LOTS.map((l) => [l.id, l])) as Record<LotId, LotDef>;

const ARCHI = new Set(
  [
    'IfcWall', 'IfcWallStandardCase', 'IfcCurtainWall', 'IfcSlab', 'IfcRoof', 'IfcWindow', 'IfcDoor', 'IfcStair', 'IfcStairFlight',
    'IfcRamp', 'IfcRampFlight', 'IfcRailing', 'IfcColumn', 'IfcBeam', 'IfcCovering', 'IfcMember', 'IfcPlate', 'IfcFooting', 'IfcPile',
    'IfcChimney', 'IfcShadingDevice', 'IfcBuildingElementPart',
  ].map((s) => s.toLowerCase()),
);

export const EQUIPMENT_CLASSES = new Set(
  [
    'IfcBoiler', 'IfcChiller', 'IfcUnitaryEquipment', 'IfcHeatExchanger', 'IfcBurner', 'IfcCoolingTower', 'IfcCondenser', 'IfcEvaporator',
    'IfcEvaporativeCooler', 'IfcCompressor', 'IfcAirToAirHeatRecovery', 'IfcHumidifier', 'IfcSolarDevice', 'IfcPump', 'IfcFan', 'IfcTank',
    'IfcUnitaryControlElement', 'IfcController', 'IfcSensor', 'IfcActuator', 'IfcElectricGenerator', 'IfcEngine', 'IfcFlowMeter',
  ].map((s) => s.toLowerCase()),
);

const VENT = new Set(['IfcDuctSegment', 'IfcDuctFitting', 'IfcDuctSilencer', 'IfcAirTerminal', 'IfcAirTerminalBox', 'IfcDamper'].map((s) => s.toLowerCase()));
const ELEC = new Set(
  [
    'IfcCableSegment', 'IfcCableCarrierSegment', 'IfcCableFitting', 'IfcCableCarrierFitting', 'IfcElectricAppliance', 'IfcElectricDistributionBoard',
    'IfcElectricMotor', 'IfcElectricTimeControl', 'IfcJunctionBox', 'IfcLightFixture', 'IfcLamp', 'IfcOutlet', 'IfcProtectiveDevice',
    'IfcSwitchingDevice', 'IfcTransformer', 'IfcElectricFlowStorageDevice',
  ].map((s) => s.toLowerCase()),
);

/** Classes considérées comme éléments de réseau (doivent appartenir à un système). */
export const MEP_CLASSES = new Set(
  [
    'IfcPipeSegment', 'IfcPipeFitting', 'IfcDuctSegment', 'IfcDuctFitting', 'IfcValve', 'IfcPump', 'IfcFan', 'IfcTank', 'IfcBoiler', 'IfcChiller',
    'IfcUnitaryEquipment', 'IfcHeatExchanger', 'IfcSpaceHeater', 'IfcAirTerminal', 'IfcSanitaryTerminal', 'IfcFilter', 'IfcDamper',
    'IfcFlowMeter', 'IfcAirToAirHeatRecovery', 'IfcFlowSegment', 'IfcFlowFitting', 'IfcFlowTerminal', 'IfcFlowController',
    'IfcFlowMovingDevice', 'IfcFlowStorageDevice', 'IfcEnergyConversionDevice', 'IfcCoil', 'IfcDuctSilencer', 'IfcWasteTerminal',
  ].map((s) => s.toLowerCase()),
);

export function lotFromSystem(predefined: string, name: string): LotId | null {
  const p = (predefined || '').toUpperCase();
  if (p === 'HEATING') return 'chauffage';
  if (p === 'DOMESTICHOTWATER') return 'ecs';
  if (p === 'DOMESTICCOLDWATER' || p === 'WATERSUPPLY') return 'ef';
  if (['VENTILATION', 'EXHAUST', 'AIRCONDITIONING', 'VENT'].includes(p)) return 'ventilation';
  if (['ELECTRICAL', 'LIGHTING', 'POWERGENERATION', 'EARTHING', 'LIGHTNINGPROTECTION'].includes(p)) return 'electrique';
  const n = (name || '').toLowerCase();
  if (/chauff|heating|radiat|plancher chauffant/.test(n)) return 'chauffage';
  if (/eau chaude|ecs|hot water|\bec\b/.test(n)) return 'ecs';
  if (/eau froide|cold water|\bef\b|alimentation eau/.test(n)) return 'ef';
  if (/ventil|vmc|extraction|soufflage|air neuf|cta/.test(n)) return 'ventilation';
  if (/[ée]lectri|courant|éclairage|eclairage/.test(n)) return 'electrique';
  if (p && p !== 'NOTDEFINED' && p !== 'USERDEFINED') return 'autres';
  return null;
}

export function classifyLot(cls: string, systemLots: LotId[], name: string): LotId {
  const c = cls.toLowerCase();
  if (c === 'ifcspace') return 'espaces';
  if (EQUIPMENT_CLASSES.has(c)) return 'equipements';
  const sys = systemLots.find((l) => l !== 'autres') ?? systemLots[0];
  if (sys) return sys;
  if (ARCHI.has(c)) return 'archi';
  if (VENT.has(c)) return 'ventilation';
  if (ELEC.has(c)) return 'electrique';
  if (c === 'ifcspaceheater') return 'chauffage';
  if (c === 'ifcsanitaryterminal') return 'ef';
  const n = name.toLowerCase();
  if (MEP_CLASSES.has(c)) {
    if (/chauff|radiat|départ|depart|retour/.test(n)) return 'chauffage';
    if (/eau chaude|ecs/.test(n)) return 'ecs';
    if (/eau froide|\bef\b/.test(n)) return 'ef';
    if (/vmc|ventil|gaine|bouche/.test(n)) return 'ventilation';
  }
  return 'autres';
}

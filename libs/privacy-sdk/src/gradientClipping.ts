/**
 * L2 Norm Clipping for gradients.
 */
export function clipGradient(gradient: number[], C: number = 1.0): number[] {
    const l2Norm = Math.sqrt(gradient.reduce((sum, val) => sum + val * val, 0));
    const factor = Math.min(1.0, C / (l2Norm + 1e-10));
    return gradient.map(val => val * factor);
}

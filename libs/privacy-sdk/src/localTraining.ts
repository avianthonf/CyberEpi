import { gradientClipping } from './gradientClipping';

/**
 * Local SGD training on device.
 * E=5 epochs.
 */
export async function trainLocalModel(
    data: any[], 
    globalParams: number[], 
    lr: number = 0.01, 
    epochs: number = 5
): Promise<number[]> {
    let localParams = [...globalParams];
    const n = data.length;

    for (let e = 0; e < epochs; e++) {
        // Mock gradient descent step
        // In a real app, this would use TensorFlow.js or similar
        const gradient = globalParams.map(() => (Math.random() - 0.5) * 0.1);
        
        for (let i = 0; i < localParams.length; i++) {
            localParams[i] -= lr * gradient[i];
        }
    }

    // Return the delta (gradient update)
    return localParams.map((p, i) => p - globalParams[i]);
}

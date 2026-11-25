import {QueryClient} from '@tanstack/react-query';

// The same client is used by the root provider and synchronous auth transitions.
export const queryClient = new QueryClient();

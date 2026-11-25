import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
  AxiosRequestConfig,
} from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  getPatientSession,
  assertPatientSession,
  type PatientSession,
} from '@/lib/patientSession';
import {ApiResponse} from '@/types';
import {authService} from './auth';
import {useAuthStore} from '@/store/authStore';

const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

export interface ApiRequestOptions {
  patientSession?: PatientSession;
  signal?: AbortSignal;
}

type ScopedConfig = InternalAxiosRequestConfig & {
  metadata?: ApiRequestOptions;
  _retry?: boolean;
};
type RequestOptions = AxiosRequestConfig & {metadata: ApiRequestOptions};

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(
      config => {
        const request = config as ScopedConfig;
        const session = request.metadata?.patientSession || getPatientSession();
        request.metadata = {...request.metadata, patientSession: session};
        assertPatientSession(session);
        let token: string | null;
        try {
          token = SecureStore.getItem('access_token');
        } catch {
          throw new Error('Stored sign-in credentials are temporarily unavailable. Please try again.');
        }
        assertPatientSession(session);
        if (token) request.headers.Authorization = `Bearer ${token}`;
        return request;
      },
      error => { throw error; },
      {synchronous: true},
    );

    this.client.interceptors.response.use(
      response => {
        const session = (response.config as ScopedConfig).metadata?.patientSession;
        if (session) assertPatientSession(session);
        return response;
      },
      async (error: AxiosError) => {
        if (!error.config) throw error;
        const request = error.config as ScopedConfig;
        const session = request.metadata?.patientSession;
        if (session) assertPatientSession(session);
        if (error.response?.status !== 401 || request._retry) throw error;
        request._retry = true;
        // Transport/5xx refresh failures throw without destroying credentials.
        const tokens = await authService.refreshAccessToken();
        if (session) assertPatientSession(session);
        if (!tokens) {
          await useAuthStore.getState().logout();
          throw new Error('Your session has expired. Please sign in again.');
        }
        request.headers.Authorization = `Bearer ${tokens.access_token}`;
        return this.client(request);
      },
    );
  }

  // Public methods
  async get<T = unknown>(
    url: string,
    params?: Record<string, unknown>,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<T>> {
    const config: RequestOptions = {
      ...(params ? {params} : {}),
      ...(options?.signal ? {signal: options.signal} : {}),
      metadata: {patientSession: options?.patientSession || getPatientSession()},
    };
    const response = await this.client.get<T>(url, config);
    return {
      data: response.data,
      status: response.status,
    };
  }

  async post<T = unknown>(
    url: string,
    data?: unknown,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<T>> {
    const config: RequestOptions = {
      ...(options?.signal ? {signal: options.signal} : {}),
      metadata: {patientSession: options?.patientSession || getPatientSession()},
    };
    const response = await this.client.post<T>(url, data, config);
    return {
      data: response.data,
      status: response.status,
    };
  }

  async put<T = unknown>(
    url: string,
    data?: unknown,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<T>> {
    const config: RequestOptions = {
      ...(options?.signal ? {signal: options.signal} : {}),
      metadata: {patientSession: options?.patientSession || getPatientSession()},
    };
    const response = await this.client.put<T>(url, data, config);
    return {
      data: response.data,
      status: response.status,
    };
  }

  async patch<T = unknown>(
    url: string,
    data?: unknown,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<T>> {
    const config: RequestOptions = {
      ...(options?.signal ? {signal: options.signal} : {}),
      metadata: {patientSession: options?.patientSession || getPatientSession()},
    };
    const response = await this.client.patch<T>(url, data, config);
    return {
      data: response.data,
      status: response.status,
    };
  }

  async delete<T = unknown>(
    url: string,
    data?: unknown,
    options?: ApiRequestOptions,
  ): Promise<ApiResponse<T>> {
    const config: RequestOptions = {
      ...(data ? {data} : {}),
      ...(options?.signal ? {signal: options.signal} : {}),
      metadata: {patientSession: options?.patientSession || getPatientSession()},
    };
    const response = await this.client.delete<T>(url, config);
    return {
      data: response.data,
      status: response.status,
    };
  }
}

export const apiClient = new ApiClient();
export default apiClient;

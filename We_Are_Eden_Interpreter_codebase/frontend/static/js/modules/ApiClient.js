export class ApiClient {
    constructor() {
        this.onError = null; // Callback for errors
        this.onProgress = null; // Callback for progress updates
        this.onStart = null; // Callback for assessment start
        this.onDocumentComplete = null; // Callback for document completion
    }

    async loadCategories() {
        try {
            const response = await fetch('/api/categories');
            if (!response.ok) throw new Error('Failed to load categories');
            
            return await response.json();
        } catch (error) {
            console.error('Error loading categories:', error);
            if (this.onError) {
                this.onError('Failed to load category information');
            }
            return null;
        }
    }

    async submitAssessment(file, category) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', category);
            
            const response = await fetch('/api/assess', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error occurred' }));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Handle SSE stream response
            return await this._handleStreamResponse(response);
            
        } catch (error) {
            console.error('Assessment error:', error);
            const errorMessage = error.message || 'Assessment failed. Please try again.';
            if (this.onError) {
                this.onError(errorMessage);
            }
            throw error;
        }
    }

    async _handleStreamResponse(response) {
        return new Promise((resolve, reject) => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            const processChunk = ({ done, value }) => {
                if (done) {
                    return;
                }

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const eventData = JSON.parse(line.slice(6));
                            this._handleSSEEvent(eventData, resolve, reject);
                        } catch (error) {
                            console.error('Error parsing SSE event:', error);
                        }
                    }
                }

                reader.read().then(processChunk).catch(reject);
            };

            reader.read().then(processChunk).catch(reject);
        });
    }

    _handleSSEEvent(event, resolve, reject) {
        switch (event.type) {
            case 'start':
                if (this.onStart) {
                    this.onStart(event);
                }
                break;

            case 'progress':
                if (this.onProgress) {
                    this.onProgress(event);
                }
                break;

            case 'document_complete':
                if (this.onDocumentComplete) {
                    this.onDocumentComplete(event);
                }
                break;

            case 'document_error':
                console.warn('Document processing error:', event.error);
                // Continue processing other documents
                break;

            case 'complete':
                resolve(event.result);
                break;

            case 'error':
                reject(new Error(event.message));
                break;

            default:
                console.log('Unknown SSE event type:', event.type);
        }
    }
}

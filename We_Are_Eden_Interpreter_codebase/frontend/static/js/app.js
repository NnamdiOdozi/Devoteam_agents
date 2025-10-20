import { FileHandler } from './modules/FileHandler.js';
import { ApiClient } from './modules/ApiClient.js';
import { UIManager } from './modules/UIManager.js';
import { ResultsRenderer } from './modules/ResultsRenderer.js';
import { ModalManager } from './modules/ModalManager.js';

class PolicyAssessmentApp {
    constructor() {
        this.initElements();
        this.initModules();
        this.setupModuleCallbacks();
        this.loadCategories();
        
        // Set initial state
        this.uiManager.showEmpty();
    }

    initElements() {
        // Collect all DOM elements
        this.elements = {
            // File upload elements
            uploadArea: document.getElementById('uploadArea'),
            fileInput: document.getElementById('fileInput'),
            uploadBtn: document.getElementById('uploadBtn'),
            fileSelected: document.getElementById('fileSelected'),
            fileName: document.getElementById('fileName'),
            fileSize: document.getElementById('fileSize'),
            removeBtn: document.getElementById('removeBtn'),
            
            // Form elements
            assessmentForm: document.getElementById('assessmentForm'),
            assessBtn: document.getElementById('assessBtn'),
            categoryRadios: document.querySelectorAll('input[name="category"]'),
            
            // Section elements
            uploadSection: document.getElementById('uploadSection'),
            loadingSection: document.getElementById('loadingSection'),
            resultsSection: document.getElementById('resultsSection'),
            errorSection: document.getElementById('errorSection'),
            emptyState: document.getElementById('emptyState'),
            
            // Progress elements
            loadingTitle: document.getElementById('loadingTitle'),
            loadingSubtitle: document.getElementById('loadingSubtitle'),
            progressFill: document.getElementById('progressFill'),
            progressCounter: document.getElementById('progressCounter'),
            progressStatus: document.getElementById('progressStatus'),
            currentDocument: document.getElementById('currentDocument'),
            documentIcon: document.getElementById('documentIcon'),
            currentDocumentName: document.getElementById('currentDocumentName'),
            currentDocumentType: document.getElementById('currentDocumentType'),
            
            // Navigation elements
            backBtn: document.getElementById('backBtn'),
            retryBtn: document.getElementById('retryBtn'),
            errorMessage: document.getElementById('errorMessage'),
            
            // Modal elements
            documentModal: document.getElementById('documentModal'),
            modalTitle: document.getElementById('modalTitle'),
            modalCloseBtn: document.getElementById('modalCloseBtn'),
            modalLegislationCount: document.getElementById('modalLegislationCount'),
            modalLegislationList: document.getElementById('modalLegislationList'),
            modalGuidelinesCount: document.getElementById('modalGuidelinesCount'),
            modalGuidelinesList: document.getElementById('modalGuidelinesList'),
            modalNewsCount: document.getElementById('modalNewsCount'),
            modalNewsList: document.getElementById('modalNewsList'),
            infoButtons: document.querySelectorAll('.info-btn'),
            
            // Results elements
            policyName: document.getElementById('policyName'),
            assessmentDate: document.getElementById('assessmentDate'),
            totalDocs: document.getElementById('totalDocs'),
            totalRecs: document.getElementById('totalRecs'),
            exportBtn: document.getElementById('exportBtn'),
            highRecommendations: document.getElementById('highRecommendations'),
            mediumRecommendations: document.getElementById('mediumRecommendations'),
            lowRecommendations: document.getElementById('lowRecommendations'),
            legislationResults: document.getElementById('legislationResults'),
            guidelinesResults: document.getElementById('guidelinesResults'),
            newsResults: document.getElementById('newsResults')
        };
    }

    initModules() {
        // Initialize all modules with required elements
        this.fileHandler = new FileHandler(this.elements);
        this.apiClient = new ApiClient();
        this.uiManager = new UIManager(this.elements);
        this.resultsRenderer = new ResultsRenderer(this.elements);
        this.modalManager = new ModalManager(this.elements);
        
        // Connect FileHandler to UIManager for file state checking
        this.uiManager.setFileHandler(this.fileHandler);
    }

    setupModuleCallbacks() {
        // File handler callbacks
        this.fileHandler.onFileChange = (file) => {
            this.uiManager.updateSubmitButton(file !== null);
        };
        this.fileHandler.onError = (message) => {
            this.uiManager.showError(message);
        };
        
        // API client callbacks
        this.apiClient.onError = (message) => {
            this.uiManager.showError(message);
        };
        
        // Progress callbacks for SSE
        this.apiClient.onStart = (event) => {
            this.uiManager.updateProgress({
                type: 'start',
                total: event.total_documents,
                policyName: event.policy_name,
                category: event.category
            });
        };
        
        this.apiClient.onProgress = (event) => {
            this.uiManager.updateProgress({
                type: 'progress',
                current: event.current_document,
                total: event.total_documents,
                documentName: event.document_name,
                documentType: event.document_type,
                message: event.message
            });
        };
        
        this.apiClient.onDocumentComplete = (event) => {
            this.uiManager.updateProgress({
                type: 'document_complete',
                current: event.current_document,
                documentName: event.document_name,
                recommendationsCount: event.recommendations_count
            });
        };
        
        // UI manager callbacks
        this.uiManager.onReset = () => {
            this.fileHandler.clearFile();
        };
        this.uiManager.onSubmit = () => {
            this.handleSubmit();
        };
        
        // Bind form submission
        this.uiManager.bindFormSubmit(this.elements.assessmentForm);
    }

    async loadCategories() {
        const categories = await this.apiClient.loadCategories();
        
        if (categories) {
            this.modalManager.setCategories(categories);
            this.modalManager.populateCategoryPreviews();
        } else {
            // Show basic category info without preview
            this.modalManager.showBasicCategoryInfo();
        }
    }

    async handleSubmit() {
        const file = this.fileHandler.getSelectedFile();
        const category = this.uiManager.getSelectedCategory();
        
        if (!file) {
            this.uiManager.showError('Please select a PDF file.');
            return;
        }

        if (!category) {
            this.uiManager.showError('Please select a policy category.');
            return;
        }

        await this.submitAssessment(file, category);
    }

    async submitAssessment(file, category) {
        try {
            this.uiManager.showLoading();
            
            const results = await this.apiClient.submitAssessment(file, category);
            this.resultsRenderer.populateResults(results);
            this.uiManager.showResults();
            
        } catch (error) {
            // Error is already handled by apiClient.onError callback
            console.error('Assessment failed:', error);
        }
    }
}

// Initialize the app when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new PolicyAssessmentApp();
});

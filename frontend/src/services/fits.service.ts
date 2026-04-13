import { Injectable, signal } from '@angular/core';

// Declaration for the global fitsjs library loaded via CDN
declare const astro: any;

export interface FitsHeaderItem {
  key: string;
  value: string | number;
  comment?: string;
}

export interface FitsData {
  header: FitsHeaderItem[];
  width: number;
  height: number;
  min: number;
  max: number;
  data: Float32Array; // Normalized data for rendering
}

@Injectable({
  providedIn: 'root'
})
export class FitsService {
  loading = signal<boolean>(false);
  error = signal<string | null>(null);

  constructor() {}

  clearError() {
    this.error.set(null);
  }

  // Parse Blob/File (Public for use with local file inputs)
  async parseBlob(blob: Blob): Promise<FitsData> {
    this.loading.set(true);
    this.error.set(null);

    if (typeof astro === 'undefined') {
        const msg = 'FITS library (fitsjs) is not loaded. Check your internet connection to CDN.';
        this.error.set(msg);
        this.loading.set(false);
        return Promise.reject(new Error(msg));
    }

    return new Promise((resolve, reject) => {
      // Use fitsjs from the CDN
      try {
        new astro.FITS(blob, () => {
            // Callback when initialization starts
        }).bind('error', (e: any) => {
            console.error('FitsJS Error:', e);
            const msg = 'Failed to parse FITS file. The file might be corrupted, not a valid FITS format, or compressed in an unsupported way.';
            this.error.set(msg);
            this.loading.set(false);
            reject(new Error(msg));
        }).bind('load', (fits: any) => {
            try {
            const hdu = fits.getHDU(0); // Get Primary HDU
            if (!hdu.data) {
                // Try extension 1 if primary is empty (common in compressed FITS)
                const extHdu = fits.getHDU(1);
                if (extHdu && extHdu.data) {
                    this.processHDU(extHdu).then(resolve).catch(reject);
                    return;
                }
                throw new Error('No image data found in FITS file (Primary HDU and Ext 1 checked).');
            }
            this.processHDU(hdu).then(resolve).catch(reject);
            } catch (err: any) {
            this.error.set(`Structure Error: ${err.message}`);
            this.loading.set(false);
            reject(err);
            }
        });
      } catch (initErr: any) {
          this.error.set(`Initialization Error: ${initErr.message}`);
          this.loading.set(false);
          reject(initErr);
      }
    });
  }

  async loadFromUrl(url: string): Promise<FitsData> {
    this.loading.set(true);
    this.error.set(null);
    try {
      if (!navigator.onLine) {
        throw new Error('No internet connection available to fetch file.');
      }

      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const blob = await response.blob();
      
      return await this.parseBlob(blob);
    } catch (e: any) {
      let msg = e.message;
      if (msg === 'Failed to fetch') {
          msg = 'CORS Error: The external server prevented access to this FITS file.';
      }
      this.error.set(`Failed to download: ${msg}`);
      this.loading.set(false);
      throw e;
    }
  }

  private async processHDU(hdu: any): Promise<FitsData> {
    try {
        const headerCards = hdu.header.cards;
        const headerList: FitsHeaderItem[] = [];
        
        // Extract header safely
        for (const key in headerCards) {
        if (Object.prototype.hasOwnProperty.call(headerCards, key)) {
            const card = headerCards[key];
            // fitsjs stores cards in a specific way
            if (Array.isArray(card)) {
            headerList.push({ key, value: card[0], comment: card[1] });
            } else {
                headerList.push({ key, value: card, comment: '' });
            }
        }
        }

        const dataUnit = hdu.data;
        let width = dataUnit.width;
        let height = dataUnit.height;
        
        if (!width || !height) {
            width = hdu.header.get('NAXIS1');
            height = hdu.header.get('NAXIS2');
        }

        // Get raw data
        const rawData = await dataUnit.getFrame(); 
        
        // Find min/max for scaling
        let min = Number.POSITIVE_INFINITY;
        let max = Number.NEGATIVE_INFINITY;
        
        // We convert to Float32 for easier rendering
        const floatData = new Float32Array(rawData.length);
        
        for (let i = 0; i < rawData.length; i++) {
            const val = rawData[i];
            floatData[i] = val;
            if (!isNaN(val)) {
                if (val < min) min = val;
                if (val > max) max = val;
            }
        }

        // Handle completely flat or NaN images
        if (min === Number.POSITIVE_INFINITY || max === Number.NEGATIVE_INFINITY) {
            min = 0;
            max = 1;
        }
        if (min === max) {
            max = min + 1; // Prevent division by zero in rendering
        }

        this.loading.set(false);

        return {
        header: headerList,
        width,
        height,
        min,
        max,
        data: floatData
        };
    } catch (processErr: any) {
        this.error.set(`Processing Error: ${processErr.message}`);
        this.loading.set(false);
        throw processErr;
    }
  }
}
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { requestAPI } from './request';

/**
 * Initialization data for the @jupyter-ai-contrib/braket extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyter-ai-contrib/braket:plugin',
  description: 'A Jupyter AI persona designed to assist AWS Braket users on quantum computing tasks.',
  autoStart: true,
  activate: (app: JupyterFrontEnd) => {
    console.log('JupyterLab extension @jupyter-ai-contrib/braket is activated!');

    requestAPI<any>('hello')
      .then(data => {
        console.log(data);
      })
      .catch(reason => {
        console.error(
          `The jupyter_ai_braket server extension appears to be missing.\n${reason}`
        );
      });
  }
};

export default plugin;

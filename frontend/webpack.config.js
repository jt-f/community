const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const webpack = require('webpack');

module.exports = {
  mode: 'development',
  entry: './src/index.tsx',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'bundle.js',
    publicPath: '/'
  },
  module: {
    rules: [
      {
        test: /\.(ts|tsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'ts-loader',
        }
      },
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env', '@babel/preset-react', '@babel/preset-typescript'],
            plugins: ['@babel/plugin-transform-runtime']
          }
        }
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader']
      }
    ]
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: './public/index.html'
    }),
    // Define environment variables that will be available in the browser
    new webpack.DefinePlugin({
      'process.env': {
        'REACT_APP_WS_URL': JSON.stringify(process.env.REACT_APP_WS_URL || 'ws://172.19.36.55:8000/ws'),
        'REACT_APP_API_URL': JSON.stringify(process.env.REACT_APP_API_URL || 'http://172.19.36.55:8000/api')
      }
    }),
    new webpack.HotModuleReplacementPlugin()
  ],
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
    modules: ['node_modules']
  },
  devServer: {
    host: '0.0.0.0',
    port: 3000,
    hot: true,
    historyApiFallback: true,
    open: false,
    client: {
      overlay: true,
      progress: true
    },
    static: {
      directory: path.join(__dirname, 'public')
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        secure: false,
        changeOrigin: true
      }
    }
  },
  cache: {
    type: 'filesystem'
  },
  optimization: {
    removeAvailableModules: false,
    removeEmptyChunks: false,
    splitChunks: false,
  }
}; 
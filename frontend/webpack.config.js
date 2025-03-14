const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const webpack = require('webpack');

module.exports = {
  mode: 'development',
  entry: './src/index.tsx',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].[contenthash].js',
    chunkFilename: '[name].[contenthash].chunk.js',
    publicPath: '/'
  },
  optimization: {
    splitChunks: {
      chunks: 'all',
      name: false, // This prevents naming conflicts
      cacheGroups: {
        vendors: {
          test: /[\\/]node_modules[\\/]/,
          priority: -10,
          reuseExistingChunk: true
        },
        default: {
          minChunks: 2,
          priority: -20,
          reuseExistingChunk: true
        }
      }
    }
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
  // Update optimization settings
  optimization: {
    removeAvailableModules: true,
    removeEmptyChunks: true,
    splitChunks: {
      chunks: 'all',
      minSize: 20000,
      maxSize: 244000,
      cacheGroups: {
        vendor: {
          test: /[\\/]node_modules[\\/]/,
          name: 'vendors',
          chunks: 'all',
        },
      },
    },
  },
  // Add performance hints
  performance: {
    hints: false
  },
  // Update cache settings
  cache: {
    type: 'filesystem',
    buildDependencies: {
      config: [__filename],
    },
    compression: 'gzip',
  },
  // Update devServer settings
  devServer: {
    host: '0.0.0.0',
    port: 3000,
    hot: true,
    historyApiFallback: true,
    open: false,
    client: {
      overlay: {
        errors: true,
        warnings: false,
      },
      progress: true,
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
};